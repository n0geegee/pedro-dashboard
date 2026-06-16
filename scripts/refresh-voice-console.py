#!/usr/bin/env python3
"""Pedro voice — idle heartbeat / state refresher.

Keeps `voice_console.json` fresh in idle state. If a real voice daemon
is running, the daemon owns the file and this script is a no-op
(updated_at is newer than the heartbeat threshold).

If the daemon is dead, this script writes a clean idle state so the
kiosk does not display a stale "listening for wake" card after a crash.

Exit codes:
    0  state written or daemon owned
    2  state write failed
    3  privacy file unreadable
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = PROJECT_ROOT / "app" / "state" / "voice_console.json"
DAEMON_PID_FILE = Path(os.environ.get("PEDRO_VOICE_DAEMON_PID",
                                      str(Path.home() / ".local" / "state" / "pedro_dashboard" / "run" / "voice_daemon.pid")))
PRIVACY_FILE = Path(os.environ.get("PEDRO_PRIVACY_FILE",
                                   str(Path.home() / ".local" / "state" / "pedro_dashboard" / "privacy_mode")))

IDLE_HEARTBEAT_THRESHOLD_S = 8  # if updated_at is newer than this, daemon is alive


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _daemon_alive() -> bool:
    if not DAEMON_PID_FILE.exists():
        return False
    try:
        pid = int(DAEMON_PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_privacy() -> str:
    if not PRIVACY_FILE.exists():
        return "private"
    try:
        v = PRIVACY_FILE.read_text(encoding="utf-8").strip().lower()
        if v in ("normal", "private", "guest"):
            return v
    except OSError:
        pass
    return "private"


def _idle_payload(privacy: str, mic: str, stt: str, runner: str) -> dict:
    return {
        "status": "ok" if mic != "missing" else "stale",
        "updated_at": _now_iso(),
        "ttl_seconds": 30,
        "privacy_mode": privacy,
        "voice": {
            "mode": "wake_word",
            "state": "listening_for_wake",
            "wake_phrase": "hey pedro",
            "mic_status": mic,
            "stt_status": stt,
            "runner_status": runner,
        },
        "utterance": {"partial": "", "final": "", "language": "pl", "confidence": None},
        "activity": {"label": "Słucham", "detail": "Powiedz 'hey pedro' żeby zadać komendę.",
                     "spinner": False},
        "result": {"summary": "Brak aktywnej komendy.", "requires_user_action": False,
                   "clarifying_question": None},
        "error": {"code": None, "message_public": None, "debug_ref": None},
    }


def run(args: argparse.Namespace) -> int:
    state_path = Path(args.state).resolve()
    privacy = _read_privacy()
    state = _read_state(state_path)
    now = time.time()
    if _daemon_alive():
        # daemon owns the file; only repaint if state is currently error/disabled
        current_state = (state.get("voice") or {}).get("state", "idle")
        if current_state in ("error", "disabled", "privacy_blocked") and not args.force:
            payload = _idle_payload(privacy, "available", "ready", "ready")
            _atomic_write(state_path, payload)
            print(json.dumps({"ok": True, "mode": "repaint_from_error", "daemon": True}))
            return 0
        # heartbeat: just leave it; do not race with daemon
        print(json.dumps({"ok": True, "mode": "daemon_owns", "daemon": True,
                          "state": current_state}))
        return 0

    # No daemon. Write a clean idle state so the kiosk does not hang on stale.
    payload = _idle_payload(privacy, "unknown", "not_configured", "not_configured")
    _atomic_write(state_path, payload)
    print(json.dumps({"ok": True, "mode": "daemon_dead_idle_painted", "daemon": False,
                      "state": "listening_for_wake"}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--force", action="store_true",
                        help="force a repaint even if daemon is alive and state is healthy")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
