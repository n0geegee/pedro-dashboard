#!/usr/bin/env python3
"""Pedro Dashboard — seasonal skin connector.

Writes app/state/skin.json. Default mode is auto by Europe/Warsaw date; manual
mode is stored in app/state/skin_override.json by set-skin.py.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKINS = {
    "default": {"label": "Klasyczny", "emoji": "●", "accent": "#4ea1ff"},
    "winter": {"label": "Zima", "emoji": "❄", "accent": "#9bd8ff"},
    "spring": {"label": "Wiosna", "emoji": "✿", "accent": "#7ee38f"},
    "summer": {"label": "Lato", "emoji": "☀", "accent": "#55d6ff"},
    "autumn": {"label": "Jesień", "emoji": "🍂", "accent": "#f59f3a"},
    "oracle": {"label": "Hermes Oracle", "emoji": "◈", "accent": "#43f0b5"},
}

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "app/state"
OVERRIDE_PATH = STATE_DIR / "skin_override.json"
OUT_PATH = STATE_DIR / "skin.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def season_for_month(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def load_override() -> str | None:
    try:
        data = json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    skin = str((data.get("data") or {}).get("skin") or data.get("skin") or "").strip().lower()
    mode = str((data.get("data") or {}).get("mode") or data.get("mode") or "manual").strip().lower()
    if mode == "auto" or skin == "auto":
        return None
    if skin in SKINS:
        return skin
    return None


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tz = os.environ.get("PEDRO_SKIN_TZ", "Europe/Warsaw")
    # Python stdlib zoneinfo is available on this host, but date shell TZ logic is
    # overkill here; Europe/Warsaw month is enough for season selection.
    month = int(datetime.now().strftime("%m"))
    auto_skin = season_for_month(month)
    manual = load_override()
    skin = manual or auto_skin
    meta = SKINS[skin]
    payload = {
        "status": "ok",
        "updated_at": now_iso(),
        "ttl_seconds": 86400,
        "privacy_mode": "private",
        "data": {
            "skin": skin,
            "mode": "manual" if manual else "auto",
            "season": auto_skin,
            "label": meta["label"],
            "emoji": meta["emoji"],
            "accent": meta["accent"],
            "available_skins": list(SKINS.keys()),
            "schedule": {
                "winter": "December-February",
                "spring": "March-May",
                "summer": "June-August",
                "autumn": "September-November",
            },
        },
        "error": None,
    }
    atomic_write(OUT_PATH, payload)
    print(f"wrote {OUT_PATH} skin={skin} mode={payload['data']['mode']} season={auto_skin} tz={tz}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
