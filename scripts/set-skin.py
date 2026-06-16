#!/usr/bin/env python3
"""Set Pedro Dashboard skin.

Usage:
  scripts/set-skin.py auto
  scripts/set-skin.py winter|spring|summer|autumn|default|oracle
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "app/state"
OVERRIDE_PATH = STATE_DIR / "skin_override.json"
REFRESH = ROOT / "scripts/refresh-season-skin.py"
ALLOWED = {"auto", "default", "winter", "spring", "summer", "autumn", "oracle"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1].strip().lower() not in ALLOWED:
        print("Usage: scripts/set-skin.py auto|default|winter|spring|summer|autumn|oracle", file=sys.stderr)
        return 64
    skin = argv[1].strip().lower()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if skin == "auto":
        if OVERRIDE_PATH.exists():
            OVERRIDE_PATH.unlink()
        print("skin override cleared; mode=auto")
    else:
        payload = {
            "status": "ok",
            "updated_at": now_iso(),
            "ttl_seconds": None,
            "privacy_mode": "private",
            "data": {"mode": "manual", "skin": skin},
            "error": None,
        }
        OVERRIDE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"skin override set: {skin}")
    subprocess.run([str(REFRESH)], cwd=str(ROOT), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
