#!/usr/bin/env python3
"""Pedro Dashboard — live weather probe for Warszawa-Służew via Open-Meteo.

Writes app/state/weather.json atomically in the same contract as the MVP mock.
No API key. No location privacy beyond the configured district label.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import atomic_write, envelope, now_iso, resolve_state_dir, write_error_envelope  # noqa: E402

WIDGET = "weather"
DEFAULT_TTL = 600
DEFAULT_TIMEOUT_S = 6
DEFAULT_LAT = 52.1727919
DEFAULT_LON = 21.0217989
DEFAULT_LABEL = "Warszawa–Służew"
DEFAULT_TIMEZONE = "Europe/Warsaw"
MAX_RESPONSE_BYTES = 128 * 1024

WEATHER_CODES_PL = {
    0: "Słonecznie",
    1: "Przeważnie słonecznie",
    2: "Częściowe zachmurzenie",
    3: "Pochmurno",
    45: "Mgła",
    48: "Mgła osadzająca szadź",
    51: "Lekka mżawka",
    53: "Mżawka",
    55: "Silna mżawka",
    56: "Marznąca mżawka",
    57: "Silna marznąca mżawka",
    61: "Lekki deszcz",
    63: "Deszcz",
    65: "Silny deszcz",
    66: "Marznący deszcz",
    67: "Silny marznący deszcz",
    71: "Lekki śnieg",
    73: "Śnieg",
    75: "Silny śnieg",
    77: "Ziarnisty śnieg",
    80: "Przelotny deszcz",
    81: "Przelotny deszcz",
    82: "Silne opady przelotne",
    85: "Przelotny śnieg",
    86: "Silny przelotny śnieg",
    95: "Burza",
    96: "Burza z gradem",
    99: "Silna burza z gradem",
}


def _deadline(_signum, _frame):
    raise TimeoutError("weather_probe_deadline")


def fetch_json(url: str, timeout_s: float) -> dict:
    old_handler = None
    timer_supported = hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")
    try:
        if timer_supported:
            old_handler = signal.signal(signal.SIGALRM, _deadline)
            signal.setitimer(signal.ITIMER_REAL, max(0.1, float(timeout_s)))
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "PedroDashboard/0.1"})
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


def weather_text(code) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "Warunki nieznane"
    return WEATHER_CODES_PL.get(c, "Warunki nieznane")


def nearest_hour_index(times: list, current_time: str | None) -> int:
    if not times:
        return 0
    if current_time and current_time in times:
        return times.index(current_time)
    # fallback: first future-ish item near current local hour string
    now_prefix = datetime.now().strftime("%Y-%m-%dT%H")
    for i, t in enumerate(times):
        if isinstance(t, str) and t.startswith(now_prefix):
            return i
    return 0


def probe(lat: float, lon: float, label: str, timezone_name: str, timeout_s: float) -> dict:
    params = {
        "latitude": f"{lat:.7f}",
        "longitude": f"{lon:.7f}",
        "timezone": timezone_name,
        "forecast_days": "1",
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "weather_code",
            "precipitation_probability",
        ]),
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    payload = fetch_json(url, timeout_s)
    cur = payload.get("current") or {}
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") if isinstance(hourly.get("time"), list) else []
    temps = hourly.get("temperature_2m") if isinstance(hourly.get("temperature_2m"), list) else []
    codes = hourly.get("weather_code") if isinstance(hourly.get("weather_code"), list) else []
    probs = hourly.get("precipitation_probability") if isinstance(hourly.get("precipitation_probability"), list) else []
    idx = nearest_hour_index(times, cur.get("time"))

    current_precip_pct = probs[idx] if idx < len(probs) else None
    hours = []
    for i in range(idx, min(idx + 5, len(times))):
        hh = str(times[i]).split("T")[-1] if i < len(times) else "--:--"
        hours.append({
            "hour": hh,
            "temp_c": temps[i] if i < len(temps) else None,
            "condition": weather_text(codes[i] if i < len(codes) else None),
        })

    return {
        "city": label,
        "source": "Open-Meteo live",
        "location": {
            "lat": lat,
            "lon": lon,
            "label": label,
            "timezone": timezone_name,
        },
        "current": {
            "temp_c": cur.get("temperature_2m"),
            "feels_like_c": cur.get("apparent_temperature"),
            "condition": weather_text(cur.get("weather_code")),
            "wind_kmh": cur.get("wind_speed_10m"),
            "humidity_pct": cur.get("relative_humidity_2m"),
            "precip_pct": current_precip_pct,
            "precipitation_mm": cur.get("precipitation"),
            "observed_at": cur.get("time"),
        },
        "hourly": hours,
        "last_health_check": now_iso(),
        "probe_source": "scripts/refresh-weather-status.py",
    }


def _public_error(exc: Exception) -> dict:
    return {
        "code": "WEATHER_PROBE_FAILED",
        "message_public": "Chwilowy problem z odświeżeniem pogody; pokazuję ostatni poprawny odczyt.",
        "debug_type": type(exc).__name__,
    }


def write_cached_on_failure(out_path: Path, ttl: int, exc: Exception) -> bool:
    """Keep the last good weather payload visible when Open-Meteo/DNS is flaky.

    Returns True when a cached OK payload was rewritten. The dashboard should
    not blank the weather card for transient network failures.
    """
    try:
        previous = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(previous, dict) or previous.get("status") != "ok":
        return False
    data = previous.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("current"), dict):
        return False
    cached = json.loads(json.dumps(data, ensure_ascii=False))
    cached["refresh_status"] = "cached_after_probe_error"
    cached["last_refresh_error"] = _public_error(exc)
    cached["last_failed_refresh_at"] = now_iso()
    if "last_success_at" not in cached:
        cached["last_success_at"] = previous.get("updated_at") or cached.get("last_health_check")
    atomic_write(out_path, envelope(WIDGET, "ok", ttl, cached, error=None))
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refresh app/state/weather.json from Open-Meteo for Warszawa-Służew.")
    p.add_argument("--out", default=None, help="output state directory")
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL)
    p.add_argument("--lat", type=float, default=float(os.environ.get("PEDRO_WEATHER_LAT", DEFAULT_LAT)))
    p.add_argument("--lon", type=float, default=float(os.environ.get("PEDRO_WEATHER_LON", DEFAULT_LON)))
    p.add_argument("--label", default=os.environ.get("PEDRO_WEATHER_LABEL", DEFAULT_LABEL))
    p.add_argument("--timezone", default=os.environ.get("PEDRO_WEATHER_TIMEZONE", DEFAULT_TIMEZONE))
    p.add_argument("--timeout", type=float, default=float(os.environ.get("PEDRO_WEATHER_TIMEOUT", DEFAULT_TIMEOUT_S)))
    args = p.parse_args(argv)

    state_dir = resolve_state_dir(args.out)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "weather.json"
    try:
        data = probe(args.lat, args.lon, args.label, args.timezone, args.timeout)
        atomic_write(out_path, envelope(WIDGET, "ok", args.ttl, data))
        print("wrote {} (status=ok, city={}, source=Open-Meteo live)".format(out_path, args.label))
        return 0
    except Exception as exc:
        log_dir = state_dir.parent / "logs"
        cached = write_cached_on_failure(out_path, args.ttl, exc)
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "refresh-weather-status.err.log").open("a", encoding="utf-8") as f:
                f.write("[{}] WEATHER_PROBE_FAILED cached={}: {!r}\n".format(now_iso(), cached, exc))
        except OSError:
            pass
        if cached:
            print("kept {} (status=ok, source=cached_after_probe_error); see app/logs/refresh-weather-status.err.log".format(out_path))
            return 0
        write_error_envelope(state_dir, WIDGET, args.ttl, "WEATHER_PROBE_FAILED", "Weather probe failed; no cached weather is available.")
        print("wrote {} (status=error); see app/logs/refresh-weather-status.err.log".format(out_path), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
