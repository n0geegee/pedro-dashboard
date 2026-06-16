#!/usr/bin/env python3
"""Pedro Dashboard — Kamila Google Calendar connector.

Reads Kamila's Google Calendar via a Pedro-specific OAuth token and writes the
existing `calendar.json` frontend contract. It intentionally exposes only a
small agenda view: time + event title + calendar color. Descriptions, meeting
links, attendees, and raw IDs are not written to dashboard state.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import atomic_write, envelope, now_iso, resolve_state_dir, write_error_envelope  # noqa: E402

WIDGET = "calendar"
DEFAULT_TTL = 300
DEFAULT_DAYS = 14
DEFAULT_MAX_EVENTS = 3
DEFAULT_TIMEZONE = "Europe/Warsaw"
TOKEN_PATH = Path.home() / ".hermes" / "pedro_calendar_token.json"


def load_google_client(token_path: Path):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/calendar"]
    creds = Credentials.from_authorized_user_file(str(token_path), scopes=scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        token_path.chmod(0o600)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def parse_event_start(value: dict, tz: ZoneInfo) -> datetime:
    raw = value.get("dateTime") or value.get("date")
    if not raw:
        return datetime.now(tz)
    if "T" not in raw:
        return datetime.fromisoformat(raw).replace(tzinfo=tz)
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(tz)


def fmt_time(start: dict, tz: ZoneInfo) -> str:
    if start.get("date") and not start.get("dateTime"):
        dt = parse_event_start(start, tz)
        return dt.strftime("%d.%m")
    dt = parse_event_start(start, tz)
    today = datetime.now(tz).date()
    if dt.date() == today:
        return dt.strftime("%H:%M")
    return dt.strftime("%d.%m %H:%M")


def event_title(ev: dict) -> str:
    title = (ev.get("summary") or "(bez tytułu)").strip()
    return title[:80] if len(title) > 80 else title


def public_error(exc: Exception) -> dict:
    return {
        "code": "KAMILA_CALENDAR_REFRESH_FAILED",
        "message_public": "Chwilowy problem z odświeżeniem kalendarza Kamili; jeśli jest cache, pokazuję ostatni odczyt.",
        "debug_type": type(exc).__name__,
    }


def write_cached_on_failure(out_path: Path, ttl: int, exc: Exception) -> bool:
    try:
        previous = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(previous, dict) or previous.get("status") != "ok":
        return False
    data = previous.get("data")
    if not isinstance(data, dict) or data.get("source_mode") != "kamila_google_calendar":
        return False
    cached = json.loads(json.dumps(data, ensure_ascii=False))
    cached["refresh_status"] = "cached_after_probe_error"
    cached["last_refresh_error"] = public_error(exc)
    cached["last_failed_refresh_at"] = now_iso()
    atomic_write(out_path, envelope(WIDGET, "ok", ttl, cached, error=None))
    return True


def probe(calendar_id: str, days: int, max_events: int, tz_name: str) -> dict:
    tz = ZoneInfo(tz_name)
    service = load_google_client(TOKEN_PATH)

    cal_list = service.calendarList().list(maxResults=250, minAccessRole="reader").execute().get("items", [])
    selected = None
    if calendar_id:
        for c in cal_list:
            if c.get("id") == calendar_id:
                selected = c
                break
    if selected is None:
        for c in cal_list:
            if c.get("primary"):
                selected = c
                break
    if selected is None and cal_list:
        selected = cal_list[0]
    if selected is None:
        raise RuntimeError("no_visible_calendars")

    cid = selected.get("id")
    now = datetime.now(tz)
    time_min = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    time_max = (now + timedelta(days=days)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    events = service.events().list(
        calendarId=cid,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=max_events + 10,
    ).execute().get("items", [])

    public_events = []
    for ev in events:
        if ev.get("status") == "cancelled":
            continue
        start = ev.get("start") or {}
        public_events.append({
            "time": fmt_time(start, tz),
            "title": event_title(ev),
            "color": selected.get("backgroundColor") or "var(--blue)",
        })
        if len(public_events) >= max_events:
            break

    return {
        "date_human": "Kalendarz Kamili — najbliższe wydarzenia",
        "events": public_events,
        "more_count": max(0, len(events) - len(public_events)),
        "source_mode": "kamila_google_calendar",
        "calendar_summary": selected.get("summary"),
        "calendar_access_role": selected.get("accessRole"),
        "can_write": selected.get("accessRole") in ("owner", "writer"),
        "time_window_days": days,
        "max_events": max_events,
        "privacy_note": "Dashboard exposes only event title and time; descriptions, guests, links, locations, and raw IDs are omitted.",
        "last_success_at": now_iso(),
        "probe_source": "scripts/refresh-kamila-calendar.py",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refresh app/state/calendar.json from Kamila's Google Calendar.")
    p.add_argument("--out", default=None)
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL)
    p.add_argument("--calendar-id", default=os.environ.get("PEDRO_KAMILA_CALENDAR_ID", ""))
    p.add_argument("--days", type=int, default=int(os.environ.get("PEDRO_KAMILA_CALENDAR_DAYS", DEFAULT_DAYS)))
    p.add_argument("--max-events", type=int, default=int(os.environ.get("PEDRO_KAMILA_CALENDAR_MAX_EVENTS", DEFAULT_MAX_EVENTS)))
    p.add_argument("--timezone", default=os.environ.get("PEDRO_KAMILA_CALENDAR_TIMEZONE", DEFAULT_TIMEZONE))
    args = p.parse_args(argv)

    state_dir = resolve_state_dir(args.out)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "calendar.json"
    try:
        data = probe(args.calendar_id, args.days, args.max_events, args.timezone)
        atomic_write(out_path, envelope(WIDGET, "ok", args.ttl, data))
        print(f"wrote {out_path} (status=ok, source=kamila_google_calendar, events={len(data['events'])}, can_write={data['can_write']})")
        return 0
    except Exception as exc:
        cached = write_cached_on_failure(out_path, args.ttl, exc)
        log_dir = state_dir.parent / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "refresh-kamila-calendar.err.log").open("a", encoding="utf-8") as f:
                f.write("[{}] KAMILA_CALENDAR_REFRESH_FAILED cached={}: {!r}\n".format(now_iso(), cached, exc))
        except OSError:
            pass
        if cached:
            print(f"kept {out_path} (status=ok, source=cached_after_probe_error)")
            return 0
        write_error_envelope(state_dir, WIDGET, args.ttl, "KAMILA_CALENDAR_REFRESH_FAILED", "Calendar refresh failed; no cached Kamila calendar is available.")
        print(f"wrote {out_path} (status=error); see app/logs/refresh-kamila-calendar.err.log", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
