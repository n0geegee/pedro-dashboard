"""Pedro Dashboard — Etap 3 OpenViking health probe.

Refreshes app/state/openviking.json with the public /health payload from the
local OpenViking server. Timeout-safe (default 3s), stdlib only (urllib),
no content lookups, no private data.

Privacy contract:
  * Hits ONLY the public /health endpoint. We never call /resources,
    /search, /context, or any content endpoint. OpenViking's /health is
    designed to be safe to call without auth and returns only version and
    health booleans.
  * We cap the response body at 16 KiB. OpenViking's /health is ~150 bytes
    in practice; anything larger is suspicious and we treat it as an error.
  * We never log the response body to disk. We log only the booleans we
    decided to surface (status, healthy, version, auth_mode).

Usage:
  python3 scripts/refresh-openviking-status.py
  python3 scripts/refresh-openviking-status.py --endpoint http://127.0.0.1:1933
  python3 scripts/refresh-openviking-status.py --ttl 60 --timeout 3
  OPENVIKING_ENDPOINT=http://127.0.0.1:1933 python3 scripts/refresh-openviking-status.py
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import (  # noqa: E402
    atomic_write,
    envelope,
    now_iso,
    resolve_state_dir,
    safe_int,
    write_error_envelope,
)

WIDGET = "openviking"
DEFAULT_TTL = 60
DEFAULT_ENDPOINT = "http://127.0.0.1:1933"
DEFAULT_HEALTH_PATH = "/health"
DEFAULT_TIMEOUT_S = 3
MAX_RESPONSE_BYTES = 16 * 1024
STATE_DIR_DEFAULT_HINT = "app/state/ next to the project root"


def _http_get_json(url: str, timeout_s: float) -> dict:
    """GET `url` with a wall-clock timeout. Returns a structured result.

    Never raises. Always returns a dict with keys:
      ok (bool), status_code (int|None), payload (dict|None), bytes_read (int),
      error (str|None), error_code (str|None).
    """
    res = {
        "ok": False,
        "status_code": None,
        "payload": None,
        "bytes_read": 0,
        "error": None,
        "error_code": None,
    }
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    old_handler = None
    timer_supported = hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")

    def _deadline(_signum, _frame):
        raise TimeoutError("openviking_health_deadline")

    try:
        if timer_supported:
            old_handler = signal.signal(signal.SIGALRM, _deadline)
            signal.setitimer(signal.ITIMER_REAL, max(0.1, float(timeout_s)))
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            res["status_code"] = int(getattr(resp, "status", 0) or 0)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            res["bytes_read"] = len(raw)
            if len(raw) > MAX_RESPONSE_BYTES:
                res["error"] = "response_too_large"
                res["error_code"] = "RESPONSE_TOO_LARGE"
                return res
            try:
                text = raw.decode("utf-8", errors="replace")
            except (UnicodeDecodeError, AttributeError):
                res["error"] = "decode_error"
                res["error_code"] = "DECODE_ERROR"
                return res
            if "json" not in ctype:
                # Try anyway, but mark it: this is unexpected for /health.
                pass
            try:
                res["payload"] = json.loads(text)
            except json.JSONDecodeError as exc:
                res["error"] = f"json_decode_error:{exc.msg}"
                res["error_code"] = "JSON_DECODE_ERROR"
                return res
            if not isinstance(res["payload"], dict):
                res["error"] = "payload_not_object"
                res["error_code"] = "PAYLOAD_NOT_OBJECT"
                res["payload"] = None
                return res
            res["ok"] = True
            return res
    except urllib.error.HTTPError as exc:
        res["status_code"] = int(getattr(exc, "code", 0) or 0)
        res["error"] = f"http_error_{res['status_code']}"
        res["error_code"] = f"HTTP_{res['status_code']}"
        return res
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Treat socket.timeout, ConnectionRefusedError, URLError uniformly.
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            res["error"] = "timeout"
            res["error_code"] = "TIMEOUT"
        elif isinstance(exc, urllib.error.URLError):
            res["error"] = f"url_error:{getattr(exc, 'reason', exc)!s}"[:200]
            res["error_code"] = "URL_ERROR"
        else:
            res["error"] = f"os_error:{type(exc).__name__}"
            res["error_code"] = "OS_ERROR"
        return res
    finally:
        if timer_supported:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)


def probe(endpoint: str, timeout_s: int) -> dict:
    url = endpoint.rstrip("/") + DEFAULT_HEALTH_PATH
    res = _http_get_json(url, timeout_s)

    if not res["ok"] or not res["payload"]:
        return {
            "service": "openviking",
            "endpoint": endpoint,
            "health_endpoint": url,
            "healthy": False,
            "status": "degraded",
            "version": None,
            "auth_mode": None,
            "last_health_check": now_iso(),
            "probe_timeout_seconds": int(timeout_s),
            "probe_source": "scripts/refresh-openviking-status.py",
            "error_code": res["error_code"],
            "note": "Health probe failed; UI will show degraded widget.",
        }

    p = res["payload"]
    # Only surface whitelisted scalar fields. Anything else in the response
    # is intentionally dropped — we do not want surprise fields like session
    # counts or recent query lists to leak into the dashboard.
    status_val = p.get("status")
    healthy_val = p.get("healthy")
    version_val = p.get("version")
    auth_mode_val = p.get("auth_mode")

    # Normalize booleans/strict types
    if not isinstance(healthy_val, bool):
        # Some servers return "ok"/"degraded" as the only signal. Coerce.
        healthy_val = (status_val == "ok")
    if not isinstance(status_val, str):
        status_val = "ok" if healthy_val else "degraded"

    return {
        "service": "openviking",
        "endpoint": endpoint,
        "health_endpoint": url,
        "status": status_val,
        "healthy": bool(healthy_val),
        "version": version_val if isinstance(version_val, (str, type(None))) else str(version_val),
        "auth_mode": auth_mode_val if isinstance(auth_mode_val, (str, type(None))) else str(auth_mode_val),
        "last_health_check": now_iso(),
        "probe_timeout_seconds": int(timeout_s),
        "probe_source": "scripts/refresh-openviking-status.py",
        "note": "Health only — no private content without explicit privacy-aware command.",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Refresh app/state/openviking.json with a timeout-safe /health probe."
    )
    p.add_argument("--out", default=None,
                   help=f"output state directory (default: {STATE_DIR_DEFAULT_HINT})")
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL,
                   help=f"ttl_seconds written into the envelope (default: {DEFAULT_TTL})")
    p.add_argument(
        "--endpoint",
        default=os.environ.get("OPENVIKING_ENDPOINT", DEFAULT_ENDPOINT),
        help=f"OpenViking base URL (default: {DEFAULT_ENDPOINT})",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("OPENVIKING_PROBE_TIMEOUT", str(DEFAULT_TIMEOUT_S))),
        help=f"wall-clock timeout in seconds (default: {DEFAULT_TIMEOUT_S})",
    )
    args = p.parse_args(argv)

    state_dir = resolve_state_dir(args.out)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "openviking.json"

    try:
        data = probe(args.endpoint, args.timeout)
        # Map OpenViking's two-state "ok" / anything-else to the envelope
        # contract: ok / stale / error / empty / disabled.
        if data.get("healthy") is True and data.get("status") == "ok":
            widget_status = "ok"
        elif data.get("healthy") is False:
            widget_status = "stale"
        else:
            widget_status = "error"
        payload = envelope(WIDGET, widget_status, args.ttl, data)
        atomic_write(out_path, payload)
        print(
            f"wrote {out_path} (status={widget_status}, healthy={data.get('healthy')}, "
            f"version={data.get('version')})"
        )
        return 0
    except Exception as exc:
        code = "PROBE_INTERNAL_ERROR"
        write_error_envelope(
            state_dir, WIDGET, args.ttl, code,
            "OpenViking probe failed unexpectedly; see app/logs/refresh-openviking-status.err.log",
        )
        log_dir = state_dir.parent / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "refresh-openviking-status.err.log").open("a", encoding="utf-8") as f:
                f.write(f"[{now_iso()}] {code}: {exc!r}\n")
        except OSError:
            pass
        print(f"wrote {out_path} (status=error) and logged traceback to app/logs/", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
