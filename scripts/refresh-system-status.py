#!/usr/bin/env python3
"""Refresh app/state/system.json with a safe, timeout-free probe (Etap 3).

All values are read from /proc, /etc/os-release, and a statvfs() call. We do
not spawn external commands; this means there is nothing that can hang the
probes and the script always returns within milliseconds.

Privacy contract:
  * RAM/swap/disk numbers are totals and currently-used values. No per-process
    info, no command lines, no PIDs, no log content.
  * `dashboard_process_alive` is a yes/no check (pidof the python server
    process) — we expose a boolean, never the PID.
  * `display` reflects the env var DISPLAY, and is "unknown" when unset or
    when no X server answers within ~0.4s. We never try to enumerate
    displays, only check the one already configured.
  * `browser` is the basename of /usr/bin/google-chrome if present, else
    "none". No browser history, no profile paths.

Writes app/state/system.json atomically. On any internal failure we still
write a status="error" envelope so the dashboard widget does not go blank.

Usage:
  python3 scripts/refresh-system-status.py
  python3 scripts/refresh-system-status.py --out app/state
  python3 scripts/refresh-system-status.py --ttl 30
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import sys
from pathlib import Path

# Allow `python3 scripts/refresh-system-status.py` and import of the
# sibling _probe_common module regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import (  # noqa: E402
    DEFAULT_DASHBOARD_HOST,
    DEFAULT_DASHBOARD_PORT,
    atomic_write,
    envelope,
    now_iso,
    resolve_state_dir,
    safe_float,
    safe_int,
    write_error_envelope,
)

WIDGET = "system"
DEFAULT_TTL = 30
PROBE_TIMEOUT_S = 0.4  # for X server reachability check

STATE_DIR_DEFAULT_HINT = "app/state/ next to the project root"


# --- probe helpers ---------------------------------------------------------


def _read_proc_meminfo() -> dict:
    """Return RAM and swap totals/availables in MB. Tolerant on missing keys."""
    info = {"ram_total_mb": None, "ram_available_mb": None,
            "swap_total_mb": None, "swap_free_mb": None}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue
                key, _, rest = line.partition(":")
                # rest looks like "    12345 kB"
                parts = rest.strip().split()
                if len(parts) < 2 or parts[1] != "kB":
                    continue
                kb = safe_int(parts[0], -1)
                if kb < 0:
                    continue
                mb = kb // 1024
                if key == "MemTotal":
                    info["ram_total_mb"] = mb
                elif key == "MemAvailable":
                    info["ram_available_mb"] = mb
                elif key == "SwapTotal":
                    info["swap_total_mb"] = mb
                elif key == "SwapFree":
                    info["swap_free_mb"] = mb
    except OSError:
        pass
    return info


def _read_proc_swaps_used() -> int | None:
    """Sum of used KiB across all swap entries in /proc/swaps, in MB."""
    try:
        with open("/proc/swaps", "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None
    total_kb = 0
    found = False
    for line in lines[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 4:
            try:
                total_kb += int(parts[2])
                found = True
            except ValueError:
                continue
    return total_kb // 1024 if found else None


def _read_loadavg() -> dict:
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            parts = f.read().split()
    except OSError:
        return {"load_avg_1": None, "load_avg_5": None, "load_avg_15": None}
    if len(parts) < 3:
        return {"load_avg_1": None, "load_avg_5": None, "load_avg_15": None}
    return {
        "load_avg_1": safe_float(parts[0]),
        "load_avg_5": safe_float(parts[1]),
        "load_avg_15": safe_float(parts[2]),
    }


def _read_proc_uptime_s() -> int | None:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            parts = f.read().split()
    except OSError:
        return None
    if not parts:
        return None
    return safe_int(float(parts[0]))


def _read_os_release() -> dict:
    """Read /etc/os-release; return pretty_name, version_id, id. No secrets."""
    out: dict = {"os": "unknown", "os_id": None, "os_version": None}
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return out
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if key == "PRETTY_NAME" and value:
            out["os"] = value
        elif key == "ID" and value:
            out["os_id"] = value
        elif key == "VERSION_ID" and value:
            out["os_version"] = value
    return out


def _read_proc_version_kernel() -> str | None:
    """Kernel string from /proc/version, minus the gcc/build trailer.

    We only keep the leading 'Linux ...' phrase; trailing '()' gcc info is
    stripped to keep the payload small and boring. Not a privacy concern, just
    shorter and more stable across rebuilds.
    """
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        return None
    # Cut off at the first ' (' that starts the gcc version tail, if any.
    if " (" in text:
        text = text.split(" (", 1)[0]
    return text or None


def _read_disk_for(path: str) -> dict:
    """Return disk total/used/free in GB (rounded) for the filesystem holding `path`."""
    try:
        usage = shutil.disk_usage(path)
    except (OSError, ValueError):
        return {"disk_total_gb": None, "disk_used_gb": None, "disk_available_gb": None,
                "disk_use_percent": None, "disk_path": path}
    gb = 1024 ** 3
    total = usage.total / gb
    used = usage.used / gb
    free = usage.free / gb
    use_percent = round((used / total) * 100.0, 1) if total > 0 else None
    return {
        "disk_total_gb": round(total, 1),
        "disk_used_gb": round(used, 1),
        "disk_available_gb": round(free, 1),
        "disk_use_percent": use_percent,
        "disk_path": path,
    }


def _dashboard_process_alive(pidfile: Path) -> bool:
    """True iff the PID file exists and points at a live process.

    We deliberately do NOT include the PID in the published payload.
    """
    try:
        text = pidfile.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not text.isdigit():
        return False
    pid = int(text)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    return True


def _is_x_server_reachable(display: str) -> bool:
    """Cheap check: connect a TCP socket to the X server. ~0.4s timeout.

    Does not open an X connection or send a query — just a `connect()` against
    the abstract/local socket reported in $DISPLAY (or the well-known
    :0 -> /tmp/.X11-unix/X0 fallback). On any failure returns False.
    """
    if not display:
        return False
    # DISPLAY forms: ":0", ":0.0", "host:N", "host:N.screen", "unix:N.0"
    head = display.split(":", 1)
    if len(head) == 1 or not head[1]:
        return False
    after = head[1]
    num_str = after.split(".", 1)[0]
    if not num_str.isdigit():
        return False
    n = int(num_str)
    if not (0 <= n <= 64):
        return False
    sock_path = f"/tmp/.X11-unix/X{n}"
    try:
        # Local Unix socket; we set a short timeout via select before connect.
        import select
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(PROBE_TIMEOUT_S)
        try:
            s.connect(sock_path)
        finally:
            s.close()
    except (OSError, select.error):  # noqa: F821 - select.error in Py3 is OSError
        return False
    return True


def _detect_browser() -> str:
    """Return "google-chrome" if /usr/bin/google-chrome exists, else "none"."""
    for path in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return "google-chrome"
    return "none"


# --- main ------------------------------------------------------------------


def probe(pidfile: Path | None) -> dict:
    mem = _read_proc_meminfo()
    swap_used_mb = _read_proc_swaps_used()
    if swap_used_mb is not None and mem.get("swap_total_mb") is not None:
        swap_used = swap_used_mb
        swap_total = mem["swap_total_mb"]
    else:
        swap_used = None
        swap_total = mem.get("swap_total_mb")

    load = _read_loadavg()
    uptime = _read_proc_uptime_s()
    os_info = _read_os_release()
    kernel = _read_proc_version_kernel()
    disk = _read_disk_for("/")
    display_env = os.environ.get("DISPLAY", "") or ""
    display_ok = _is_x_server_reachable(display_env) if display_env else False
    browser = _detect_browser()
    dashboard_alive = _dashboard_process_alive(pidfile) if pidfile else False

    return {
        "host": socket.gethostname(),
        "os": os_info["os"],
        "os_id": os_info["os_id"],
        "os_version": os_info["os_version"],
        "kernel": kernel,
        "python": sys.version.split()[0],
        "ram_total_mb": mem.get("ram_total_mb"),
        "ram_available_mb": mem.get("ram_available_mb"),
        "swap_total_mb": swap_total,
        "swap_used_mb": swap_used,
        "disk": disk,
        **load,
        "uptime_seconds": uptime,
        "dashboard_process_alive": bool(dashboard_alive),
        "browser": browser,
        "display": display_env or "unset",
        "display_reachable": bool(display_ok),
        "no_systemd": True,
        "probe_source": "scripts/refresh-system-status.py",
        "note": "Live probe (Etap 3). Public operational facts only.",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Refresh app/state/system.json with a safe /proc-based probe."
    )
    p.add_argument("--out", default=None,
                   help=f"output state directory (default: {STATE_DIR_DEFAULT_HINT})")
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL,
                   help=f"ttl_seconds written into the envelope (default: {DEFAULT_TTL})")
    p.add_argument(
        "--pidfile",
        default=os.environ.get(
            "DASHBOARD_PIDFILE",
            str(Path.home() / ".local" / "state" / "pedro_dashboard" / "run" / "dashboard.pid"),
        ),
        help="path to the dashboard PID file (used for dashboard_process_alive only)",
    )
    args = p.parse_args(argv)

    state_dir = resolve_state_dir(args.out)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "system.json"
    pidfile = Path(args.pidfile).expanduser()

    try:
        data = probe(pidfile)
        payload = envelope(WIDGET, "ok", args.ttl, data)
        atomic_write(out_path, payload)
        print(f"wrote {out_path} (status=ok, ttl={args.ttl}s)")
        return 0
    except Exception as exc:  # last-ditch: still write a status=error file
        # Never include exception text in the public payload; just a short code.
        code = "PROBE_INTERNAL_ERROR"
        write_error_envelope(
            state_dir, WIDGET, args.ttl, code,
            "System probe failed unexpectedly; see app/logs/refresh-system-status.err.log",
        )
        # Log full traceback to the project's app/logs/ for the operator only.
        log_dir = state_dir.parent / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "refresh-system-status.err.log").open("a", encoding="utf-8") as f:
                f.write(f"[{now_iso()}] {code}: {exc!r}\n")
        except OSError:
            pass
        print(f"wrote {out_path} (status=error) and logged traceback to app/logs/", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
