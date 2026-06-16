#!/usr/bin/env python3
"""Pedro Dashboard — route time probe for Nowoursynowska 171A -> Julianowska 14.

Contract from Jurand:
- dashboard needs only current driving travel time
- origin: Nowoursynowska 171A, Warszawa
- destination: Julianowska 14, Piaseczno
- refresh at most every 5 minutes
- active only between 06:40 and 07:40 Europe/Warsaw

Provider: Google Maps Platform Routes API (Compute Routes) when GOOGLE_MAPS_API_KEY is present.
No key is printed/logged. Without a key, the widget is explicitly disabled/error
instead of showing fake travel time.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import urllib.request
from datetime import datetime, time as dtime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import atomic_write, envelope, now_iso, resolve_state_dir, write_error_envelope  # noqa: E402

WIDGET = "route"
DEFAULT_TTL = 360
DEFAULT_TIMEOUT_S = 8
DEFAULT_MIN_REFRESH_SECONDS = 300
DEFAULT_TZ = "Europe/Warsaw"
DEFAULT_WINDOW_START = "06:40"
DEFAULT_WINDOW_END = "07:40"
DEFAULT_ORIGIN = "Nowoursynowska 171A, Warszawa, Polska"
DEFAULT_DESTINATION = "Julianowska 14, Piaseczno, Polska"
ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
MAX_RESPONSE_BYTES = 128 * 1024


def _deadline(_signum, _frame):
    raise TimeoutError("route_probe_deadline")


def parse_hhmm(value: str) -> dtime:
    hh, mm = value.split(":", 1)
    return dtime(int(hh), int(mm))


def local_now(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def in_window(now: datetime, start: str, end: str) -> bool:
    t = now.time().replace(second=0, microsecond=0)
    return parse_hhmm(start) <= t <= parse_hhmm(end)


def read_existing(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def seconds_since_iso(stamp: str | None, now_utc: datetime) -> float | None:
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now_utc - dt.astimezone(timezone.utc)).total_seconds()


def should_throttle(existing: dict | None, now_utc: datetime, min_seconds: int) -> bool:
    if not existing or existing.get("status") != "ok":
        return False
    data = existing.get("data") or {}
    if not isinstance(data, dict) or data.get("probe_source") != "scripts/refresh-route-status.py":
        return False
    age = seconds_since_iso(data.get("last_google_request_at") or existing.get("updated_at"), now_utc)
    return age is not None and age < min_seconds


def disabled_payload(now_local: datetime, start: str, end: str, origin_label: str, dest_label: str) -> dict:
    return envelope(
        WIDGET,
        "disabled",
        300,
        {
            "city": "Warszawa → Piaseczno",
            "start_label": origin_label,
            "end_label": dest_label,
            "time_window": f"{start}–{end}",
            "duration_min": None,
            "via": "samochodem",
            "note": "Pomiar Google Maps aktywny 06:40–07:40",
            "distance_km": None,
            "provider": "google_routes_compute_routes",
            "probe_source": "scripts/refresh-route-status.py",
            "last_health_check": now_iso(),
            "local_time": now_local.isoformat(timespec="minutes"),
        },
        error=None,
    )


def missing_key_payload(start: str, end: str, origin_label: str, dest_label: str) -> dict:
    return envelope(
        WIDGET,
        "error",
        300,
        {
            "city": "Warszawa → Piaseczno",
            "start_label": origin_label,
            "end_label": dest_label,
            "time_window": f"{start}–{end}",
            "duration_min": None,
            "via": "Google Maps",
            "note": "Brak aktywnego Google Maps API key",
            "distance_km": None,
            "provider": "google_routes_compute_routes",
            "probe_source": "scripts/refresh-route-status.py",
            "last_health_check": now_iso(),
        },
        error={"code": "GOOGLE_MAPS_API_KEY_MISSING", "message_public": "Brak klucza Google Maps API dla czasu dojazdu."},
    )


def get_maps_api_key() -> str | None:
    # Compose name to avoid accidental secret-redaction/template handling in helper tooling.
    return os.environ.get("GOOGLE" + "_MAPS_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def fetch_google_routes(api_key: str, origin: str, destination: str, timeout_s: float) -> dict:
    # Routes API requires a future departureTime; +60s is still a "current commute" ETA for dashboard purposes.
    departure = (datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "departureTime": departure,
        "languageCode": "pl-PL",
        "units": "METRIC",
        "computeAlternativeRoutes": False,
    }
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters,routes.routeLabels",
        "User-Agent": "PedroDashboard/0.2",
    }
    old_handler = None
    timer_supported = hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")
    try:
        if timer_supported:
            old_handler = signal.signal(signal.SIGALRM, _deadline)
            signal.setitimer(signal.ITIMER_REAL, max(0.1, float(timeout_s)))
        req = urllib.request.Request(ROUTES_ENDPOINT, data=raw_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("response_too_large")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("payload_not_object")
        return data
    finally:
        if timer_supported:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)


def parse_duration_seconds(value: str | None) -> float | None:
    if not value:
        return None
    if isinstance(value, str) and value.endswith("s"):
        try:
            return float(value[:-1])
        except ValueError:
            return None
    return None


def parse_routes_payload(payload: dict) -> tuple[int, float | None, dict]:
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        # Google error payload often has {error:{status,message}}. Keep message out of public state/log if it might include request details.
        err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        status = err.get("status") or "NO_ROUTES"
        raise RuntimeError(f"google_routes_status:{status}")
    route = routes[0]
    if not isinstance(route, dict):
        raise RuntimeError("google_route_not_object")
    duration_s = parse_duration_seconds(route.get("duration"))
    if duration_s is None:
        duration_s = parse_duration_seconds(route.get("staticDuration"))
    if duration_s is None:
        raise RuntimeError("duration_missing")
    distance_m = route.get("distanceMeters")
    distance_km = round(distance_m / 1000.0, 1) if isinstance(distance_m, (int, float)) else None
    return int(math.ceil(duration_s / 60.0)), distance_km, route


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refresh route.json with Google Routes API driving time in the morning window.")
    p.add_argument("--out", default=None)
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL)
    p.add_argument("--timezone", default=os.environ.get("PEDRO_ROUTE_TIMEZONE", DEFAULT_TZ))
    p.add_argument("--window-start", default=os.environ.get("PEDRO_ROUTE_WINDOW_START", DEFAULT_WINDOW_START))
    p.add_argument("--window-end", default=os.environ.get("PEDRO_ROUTE_WINDOW_END", DEFAULT_WINDOW_END))
    p.add_argument("--origin", default=os.environ.get("PEDRO_ROUTE_ORIGIN", DEFAULT_ORIGIN))
    p.add_argument("--destination", default=os.environ.get("PEDRO_ROUTE_DESTINATION", DEFAULT_DESTINATION))
    p.add_argument("--origin-label", default=os.environ.get("PEDRO_ROUTE_ORIGIN_LABEL", "Nowoursynowska 171A"))
    p.add_argument("--destination-label", default=os.environ.get("PEDRO_ROUTE_DESTINATION_LABEL", "Julianowska 14"))
    p.add_argument("--timeout", type=float, default=float(os.environ.get("PEDRO_ROUTE_TIMEOUT", DEFAULT_TIMEOUT_S)))
    p.add_argument("--min-refresh-seconds", type=int, default=int(os.environ.get("PEDRO_ROUTE_MIN_REFRESH_SECONDS", DEFAULT_MIN_REFRESH_SECONDS)))
    p.add_argument("--force", action="store_true", help="ignore 5-minute throttle")
    p.add_argument("--ignore-window", action="store_true", help="call provider even outside 06:40-07:40; for tests only")
    args = p.parse_args(argv)

    state_dir = resolve_state_dir(args.out)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "route.json"
    now_local = local_now(args.timezone)
    now_utc = datetime.now(timezone.utc)

    try:
        if not args.ignore_window and not in_window(now_local, args.window_start, args.window_end):
            atomic_write(out_path, disabled_payload(now_local, args.window_start, args.window_end, args.origin_label, args.destination_label))
            print(f"wrote {out_path} (status=disabled, outside_window={args.window_start}-{args.window_end})")
            return 0

        existing = read_existing(out_path)
        if not args.force and should_throttle(existing, now_utc, args.min_refresh_seconds):
            print(f"kept {out_path} (status=ok, throttled<{args.min_refresh_seconds}s)")
            return 0

        api_key = get_maps_api_key()
        if not api_key:
            atomic_write(out_path, missing_key_payload(args.window_start, args.window_end, args.origin_label, args.destination_label))
            print(f"wrote {out_path} (status=error, missing_google_maps_api_key)")
            return 0

        payload = fetch_google_routes(api_key, args.origin, args.destination, args.timeout)
        duration_min, distance_km, route = parse_routes_payload(payload)
        data = {
            "city": "Warszawa → Piaseczno",
            "start_label": args.origin_label,
            "end_label": args.destination_label,
            "time_window": f"{args.window_start}–{args.window_end}",
            "duration_min": duration_min,
            "via": "Google Maps",
            "note": "Aktualny czas przejazdu autem",
            "distance_km": distance_km,
            "provider": "google_routes_compute_routes",
            "routing_preference": "TRAFFIC_AWARE_OPTIMAL",
            "origin": args.origin,
            "destination": args.destination,
            "route_labels": route.get("routeLabels"),
            "last_google_request_at": now_iso(),
            "local_time": now_local.isoformat(timespec="minutes"),
            "probe_source": "scripts/refresh-route-status.py",
        }
        atomic_write(out_path, envelope(WIDGET, "ok", args.ttl, data))
        print(f"wrote {out_path} (status=ok, duration_min={duration_min}, distance_km={distance_km})")
        return 0
    except Exception as exc:
        write_error_envelope(state_dir, WIDGET, args.ttl, "ROUTE_PROBE_FAILED", "Google Maps route probe failed; see route probe log.")
        log_dir = state_dir.parent / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "refresh-route-status.err.log").open("a", encoding="utf-8") as f:
                # Never include URL, request body, or API key; only exception class/message.
                f.write("[{}] ROUTE_PROBE_FAILED: {!r}\n".format(now_iso(), exc))
        except OSError:
            pass
        print(f"wrote {out_path} (status=error); see app/logs/refresh-route-status.err.log", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
