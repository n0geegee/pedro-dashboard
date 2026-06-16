#!/usr/bin/env python3
"""Refresh app/state/hermes.json with a safe, timeout-bounded probe (Etap 3).

The probe has exactly two sources of public operational data:

  1. `hermes-gateway-watchdog.sh status` — invoked with a hard wall-clock
     timeout (default 3s, override with HERMES_PROBE_TIMEOUT). We parse the
     handful of public labels it prints ("watchdog daemon: running",
     "gateway:") into booleans. We do not capture or echo raw log lines.
  2. A loopback TCP connect to the gateway UI port (default 40219) — we only
     record a boolean "port_open". We never read or send bytes.

Privacy contract:
  * No raw log paths, no gateway PID, no .env content, no platform/auth
    state, no error_message strings from gateway_state.json. Public
    availability only.
  * If the watchdog status output is unexpectedly large, we cap it to
    4 KiB and stop parsing. We never echo it into the dashboard payload.
  * If the watchdog script is missing, the script still writes
    status="error" with a short public message; the dashboard then shows
    the widget as degraded instead of empty.

Usage:
  python3 scripts/refresh-hermes-status.py
  python3 scripts/refresh-hermes-status.py --out app/state
  python3 scripts/refresh-hermes-status.py --ttl 60
  HERMES_PROBE_TIMEOUT=5 python3 scripts/refresh-hermes-status.py
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
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

WIDGET = "hermes"
DEFAULT_TTL = 60
DEFAULT_UI_PORT = 40219
MAX_STATUS_OUTPUT_BYTES = 4096  # hard cap on what we'll even read from the status command
DEFAULT_TIMEOUT_S = 3
STATE_DIR_DEFAULT_HINT = "app/state/ next to the project root"


def _is_port_open(host: str, port: int, timeout_s: float) -> bool:
    """True iff a TCP connect() to host:port succeeds within timeout_s."""
    if not (0 < port < 65536):
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout_s)
            try:
                s.connect((host, port))
            except (OSError, socket.timeout):
                return False
        return True
    except (OSError, socket.gaierror):
        return False


def _read_watchdog_status(script_path: Path, timeout_s: int) -> dict:
    """Run `hermes-gateway-watchdog.sh status` with a hard wall-clock timeout.

    Returns a dict with: present (bool), watchdog_daemon (str|None),
    gateway_process (str|None), error (str|None). We never include the raw
    stdout in the public payload — only the parsed booleans and the line
    count, so even a future regression that leaks log paths stays safe.
    """
    out: dict = {
        "present": script_path.exists() and os.access(script_path, os.X_OK),
        "watchdog_daemon": None,   # "running" | "not_running" | "stale_pid"
        "gateway_process": None,   # "running" | "not_running" | "unknown"
        "raw_line_count": 0,
        "timed_out": False,
        "error": None,
    }
    if not out["present"]:
        out["error"] = "watchdog_script_missing"
        return out

    try:
        proc = subprocess.run(
            [str(script_path), "status"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        out["timed_out"] = True
        out["error"] = "watchdog_status_timeout"
        return out
    except (OSError, ValueError) as exc:
        out["error"] = f"watchdog_status_failed:{type(exc).__name__}"
        return out

    # Hard cap. Truncate to MAX_STATUS_OUTPUT_BYTES, then count lines.
    stdout = (proc.stdout or "")[:MAX_STATUS_OUTPUT_BYTES]
    out["raw_line_count"] = stdout.count("\n")

    # We only look for the public labels. The actual structure of the
    # `status` output is:
    #   watchdog daemon:
    #     PID ... bash ... hermes-gateway-watchdog.sh daemon    -> running
    #   gateway:
    #     PID ... hermes gateway run                              -> running
    # We do not match anything more; that is enough to drive the dashboard.
    in_watchdog_section = False
    in_gateway_section = False
    watchdog_running = False
    watchdog_stale = False
    gateway_running = False
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped == "watchdog daemon:":
            in_watchdog_section = True
            in_gateway_section = False
            continue
        if stripped == "gateway:":
            in_gateway_section = True
            in_watchdog_section = False
            continue
        if stripped.startswith("logs:"):
            in_watchdog_section = False
            in_gateway_section = False
            continue
        if in_watchdog_section and stripped:
            if "hermes-gateway-watchdog.sh daemon" in stripped or "watchdog-watchdog" in stripped:
                watchdog_running = True
            if "stale pid" in stripped:
                watchdog_stale = True
        if in_gateway_section and stripped and "hermes gateway run" in stripped:
            gateway_running = True

    if watchdog_stale:
        out["watchdog_daemon"] = "stale_pid"
    elif watchdog_running:
        out["watchdog_daemon"] = "running"
    else:
        # present but not running and not stale: either "not running" line or
        # an unknown structure
        out["watchdog_daemon"] = "not_running" if not watchdog_running else "running"

    if gateway_running:
        out["gateway_process"] = "running"
    else:
        out["gateway_process"] = "not_running"

    return out


def probe(script_path: Path, ui_host: str, ui_port: int, timeout_s: int) -> dict:
    status = _read_watchdog_status(script_path, timeout_s)
    port_open = _is_port_open(ui_host, ui_port, max(0.2, min(2.0, timeout_s)))

    # Overall widget status. Conservative: error if we have no evidence
    # either way; degraded if the script is missing; ok only if both
    # watchdog reports running AND the UI port is open.
    if status.get("error") == "watchdog_script_missing":
        overall = "degraded"
    elif status.get("timed_out"):
        overall = "stale"
    elif status.get("watchdog_daemon") == "running" and status.get("gateway_process") == "running" and port_open:
        overall = "ok"
    elif status.get("gateway_process") == "running" and port_open:
        # gateway up but watchdog not yet attached — still usable
        overall = "ok"
    else:
        overall = "degraded"

    return {
        "service": "hermes-gateway",
        "watchdog_daemon": status.get("watchdog_daemon"),
        "gateway_process": status.get("gateway_process"),
        "ui_endpoint_local": f"http://{ui_host}:{ui_port}",
        "ui_port_open": bool(port_open),
        "ui_port": int(ui_port),
        "last_health_check": now_iso(),
        "probe_timeout_seconds": int(timeout_s),
        "probe_source": "scripts/refresh-hermes-status.py",
        "note": "Public availability only. No raw logs, no session text.",
        # Internal field, surfaced as _meta in the envelope (not in widget data)
        "_probe_status": {
            "timed_out": bool(status.get("timed_out")),
            "error": status.get("error"),
            "status_line_count": int(status.get("raw_line_count", 0)),
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Refresh app/state/hermes.json with a safe, timeout-bounded probe."
    )
    p.add_argument("--out", default=None,
                   help=f"output state directory (default: {STATE_DIR_DEFAULT_HINT})")
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL,
                   help=f"ttl_seconds written into the envelope (default: {DEFAULT_TTL})")
    p.add_argument(
        "--watchdog",
        default=os.environ.get(
            "HERMES_WATCHDOG_SCRIPT",
            str(Path.home() / "hermes-gateway-watchdog.sh"),
        ),
        help="path to hermes-gateway-watchdog.sh (status subcommand is used)",
    )
    p.add_argument(
        "--ui-host",
        default=os.environ.get("HERMES_UI_HOST", "127.0.0.1"),
        help="gateway UI host (default: 127.0.0.1)",
    )
    p.add_argument(
        "--ui-port",
        type=int,
        default=safe_int(os.environ.get("HERMES_UI_PORT", str(DEFAULT_UI_PORT)), DEFAULT_UI_PORT),
        help=f"gateway UI port (default: {DEFAULT_UI_PORT})",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("HERMES_PROBE_TIMEOUT", str(DEFAULT_TIMEOUT_S))),
        help=f"wall-clock timeout for the status call in seconds (default: {DEFAULT_TIMEOUT_S})",
    )
    args = p.parse_args(argv)

    state_dir = resolve_state_dir(args.out)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "hermes.json"

    script_path = Path(args.watchdog).expanduser()

    try:
        data = probe(script_path, args.ui_host, args.ui_port, args.timeout)
        # Pull _meta out of data; we expose it as an envelope sibling, not in data.
        meta = data.pop("_probe_status", None)
        # overall widget status: "ok" or "stale" or "degraded" — the server's
        # load_widget() contract accepts "ok"/"stale"/"error"/"empty"/"disabled".
        # We map "degraded" -> "stale" so the operator sees a yellow indicator.
        widget_status = "ok" if data.get("watchdog_daemon") == "running" and data.get("ui_port_open") else "stale"
        if data.get("service") is None:
            widget_status = "error"
        payload = envelope(WIDGET, widget_status, args.ttl, data)
        if meta is not None:
            payload["_probe_status"] = meta  # operator-visible, not a secret
        atomic_write(out_path, payload)
        print(
            f"wrote {out_path} (status={widget_status}, "
            f"watchdog={data.get('watchdog_daemon')}, "
            f"port_open={data.get('ui_port_open')})"
        )
        return 0
    except Exception as exc:
        code = "PROBE_INTERNAL_ERROR"
        write_error_envelope(
            state_dir, WIDGET, args.ttl, code,
            "Hermes probe failed unexpectedly; see app/logs/refresh-hermes-status.err.log",
        )
        log_dir = state_dir.parent / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "refresh-hermes-status.err.log").open("a", encoding="utf-8") as f:
                f.write(f"[{now_iso()}] {code}: {exc!r}\n")
        except OSError:
            pass
        print(f"wrote {out_path} (status=error) and logged traceback to app/logs/", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
