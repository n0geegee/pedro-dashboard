#!/usr/bin/env python3
"""Refresh normalized CEV EuroVolley 2026 state for the dashboard.

The state refresher calls this script frequently, but the official CEV pages
are fetched at most once per EUROVOLLEY_SOURCE_CACHE_SECONDS (default 900s).
A failed refresh keeps the last good schedule and marks the envelope stale.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from eurovolley_schedule import SOURCES, build_data, parse_cev_final_page

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "app" / "state" / "eurovolley.json"
USER_AGENT = "PedroDashboard/EuroVolley2026 (+https://www.cev.eu/)"
DEFAULT_CACHE_SECONDS = 15 * 60


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_stamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def load_existing() -> Dict[str, Any] | None:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=20) as response:
        body = response.read()
    if not body:
        raise RuntimeError("empty official CEV response")
    return body.decode("utf-8", "replace")


def write_json(payload: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="eurovolley-", suffix=".json", dir=str(STATE_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(name, STATE_PATH)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def cached_envelope(existing: Dict[str, Any], failed_at: str, exc: Exception) -> Dict[str, Any]:
    out = dict(existing)
    out["status"] = "stale"
    out["updated_at"] = failed_at
    out["ttl_seconds"] = 86400
    data = dict(out.get("data") or {})
    freshness = dict(data.get("freshness") or {})
    freshness.update({
        "refresh_status": "cached_after_probe_error",
        "last_failed_refresh_at": failed_at,
        "last_refresh_error": {
            "code": "CEV_FETCH_FAILED",
            "debug_type": type(exc).__name__,
            "message_public": "Oficjalne źródło CEV chwilowo niedostępne.",
        },
    })
    data["freshness"] = freshness
    out["data"] = data
    out["error"] = {
        "code": "CEV_FETCH_FAILED",
        "message_public": "Oficjalny terminarz CEV jest chwilowo nieświeży.",
    }
    return out


def main() -> int:
    existing = load_existing()
    force = os.environ.get("EUROVOLLEY_FORCE", "").lower() in {"1", "true", "yes"}
    cache_seconds = float(os.environ.get("EUROVOLLEY_SOURCE_CACHE_SECONDS", DEFAULT_CACHE_SECONDS))
    previous_success = parse_stamp(((existing or {}).get("data") or {}).get("freshness", {}).get("last_success_at"))
    current = datetime.now(timezone.utc)
    if not force and existing and previous_success and (current - previous_success).total_seconds() < cache_seconds:
        print("eurovolley: source cache still fresh")
        return 0

    retrieved_at = now_iso()
    try:
        dynamic: List[Dict[str, Any]] = []
        for gender in ("K", "M"):
            html = fetch(SOURCES[gender]["official_url"])
            rows = parse_cev_final_page(html, gender, retrieved_at)
            if not rows:
                raise RuntimeError(f"official CEV {gender} page yielded no concrete match cards")
            dynamic.extend(rows)
        data = build_data(dynamic, retrieved_at, current)
        payload = {
            "status": "ok",
            "updated_at": retrieved_at,
            "ttl_seconds": 86400,
            "data": data,
            "error": None,
        }
        write_json(payload)
        print(
            "eurovolley: refreshed official CEV pages; "
            f"dynamic_matches={len(dynamic)} poland_matches={len(data['poland_matches'])}"
        )
        return 0
    except (HTTPError, URLError, OSError, RuntimeError, ValueError) as exc:
        if existing and isinstance(existing.get("data"), dict):
            write_json(cached_envelope(existing, retrieved_at, exc))
            print(f"eurovolley: kept cached state after {type(exc).__name__}", flush=True)
            return 0
        print(f"eurovolley: initial official fetch failed: {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
