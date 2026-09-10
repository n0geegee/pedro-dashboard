#!/usr/bin/env python3
"""Operator switch for the Pedro Dashboard fullscreen slideshow.

Examples:
    scripts/slideshow on
    scripts/slideshow off
    scripts/slideshow status
    scripts/slideshow restart-cycle

The command writes only the local display-control file.  The browser consumes
that file through the read-only dashboard API; the rotator is supervised here
and again by the normal no-systemd refresher loop.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import DISPLAY_CONTROL_FILE  # noqa: E402
from app.display_control import (  # noqa: E402
    ControlStateError,
    apply_action,
    control_envelope,
    read_control_state,
)

ROTATOR_SCRIPT = Path(
    os.environ.get("PEDRO_PHOTOS_ROTATOR_SCRIPT", str(SCRIPT_DIR / "photos-rotator.sh"))
).expanduser()


def _rotator_command(action: str, interval: int) -> list[str]:
    return [str(ROTATOR_SCRIPT), f"--{action}", "--interval", str(interval)]


def _run_rotator(action: str, interval: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _rotator_command(action, interval),
        text=True,
        capture_output=True,
        check=False,
    )


def sync_rotator() -> int:
    """Make the supervised photo loop match the persisted switch state."""
    result = read_control_state(DISPLAY_CONTROL_FILE)
    interval = int(result.state["photo_seconds"])
    action = "start" if result.valid and result.state["enabled"] else "stop"
    completed = _run_rotator(action, interval)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "rotator command failed").strip()
        print(f"slideshow: rotator {action} failed: {detail}", file=sys.stderr)
        return completed.returncode or 1
    return 0


def rotator_running() -> bool:
    try:
        return _run_rotator("status", 2).returncode == 0
    except OSError:
        return False


def print_status() -> int:
    result = read_control_state(DISPLAY_CONTROL_FILE)
    payload = control_envelope(DISPLAY_CONTROL_FILE)
    payload["rotator_running"] = rotator_running()
    payload["valid"] = result.valid
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    # Accept the natural operator form when called directly as
    # `pedro-display-switch.py slideshow on` as well as `scripts/slideshow on`.
    if args and args[0].lower() == "slideshow":
        args = args[1:]
    action = args[0].lower() if args else "status"
    if len(args) != 1 or action not in {"status", "on", "off", "restart-cycle", "sync"}:
        print(
            "usage: slideshow {status|on|off|restart-cycle}"
            " (internal: sync)",
            file=sys.stderr,
        )
        return 64
    if action == "status":
        return print_status()
    if action == "sync":
        return sync_rotator()
    try:
        state, changed, _ = apply_action(action, DISPLAY_CONTROL_FILE)
    except (ControlStateError, OSError) as exc:
        print(f"slideshow: control state update failed: {exc}", file=sys.stderr)
        return 1
    sync_rc = sync_rotator()
    result = {
        "action": action,
        "changed": changed,
        "enabled": state["enabled"],
        "generation": state["generation"],
        "cycle_started_at": state["cycle_started_at"],
        "photo_seconds": state["photo_seconds"],
        "rotator_sync_rc": sync_rc,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return sync_rc


if __name__ == "__main__":
    raise SystemExit(main())
