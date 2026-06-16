#!/usr/bin/env python3
"""Pedro Dashboard — Polsat Box Go UR status connector.

This does not scrape or extract video streams. It only records the legal
Polsat Box Go web entrypoint and whether the dedicated Chrome profile/window
appears to be running on the Pedro display.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import atomic_write, now_iso, resolve_state_dir  # noqa: E402

WIDGET = "media"
DEFAULT_TTL = 120
POLSAT_URL = "https://polsatboxgo.pl/kanaly-tv/polsat-sport-1/1456452"
PROFILE_DIR = str(Path.home() / ".local/share/pedro-polsat-profile")
LAUNCHER = "scripts/launch-polsat-box-go.sh"


def out_path(state_dir: Path) -> Path:
    return state_dir / "media.json"


def load_media(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {
        "status": "ok",
        "updated_at": now_iso(),
        "ttl_seconds": DEFAULT_TTL,
        "privacy_mode": "private",
        "data": {},
        "error": None,
    }


def polsat_window_running() -> bool:
    try:
        proc = subprocess.run(
            ["pgrep", "-af", "pedro-polsat-profile|polsatboxgo.pl"],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refresh Polsat Box Go status in media.json.")
    p.add_argument("--out", default=None)
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL)
    args = p.parse_args(argv)

    state_dir = resolve_state_dir(args.out)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = out_path(state_dir)
    media = load_media(path)
    data = media.setdefault("data", {})
    running = polsat_window_running()
    data["transmission"] = {
        "provider": "polsat_box_go_web",
        "mode": "external_chrome_profile",
        "channel": "Polsat Sport 1",
        "title": "Polsat Sport 1 przez Polsat Box Go",
        "status_label": "OKNO OTWARTE" if running else "GOTOWE DO LOGOWANIA",
        "live": running,
        "url": POLSAT_URL,
        "launcher": LAUNCHER,
        "profile_dir": PROFILE_DIR,
        "legal_note": "Use the normal Polsat Box Go website/account; do not extract or bypass streams/DRM.",
        "last_health_check": now_iso(),
    }
    media["status"] = "ok"
    media["updated_at"] = now_iso()
    media["ttl_seconds"] = args.ttl
    media["error"] = None
    atomic_write(path, media)
    print(f"wrote {path} (polsat_running={running})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
