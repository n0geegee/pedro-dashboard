#!/usr/bin/env python3
"""Pedro Dashboard — Poland volleyball match calendar.

Source-backed curated schedule for VNL 2026, filtered to upcoming matches.
This connector owns `volleyball.json` only. The dashboard calendar card is owned
by `refresh-kamila-calendar.py` and should not be overwritten by match data.
Update SCHEDULE / RECENT_RESULTS when sources change; do not fake live API data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import atomic_write, envelope, now_iso, resolve_state_dir  # noqa: E402

TZ = ZoneInfo("Europe/Warsaw")
WEEKDAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]

SOURCES = [
    "TVP Sport: Liga Narodów siatkarzy 2026 – terminarz reprezentacji Polski",
    "Polsat Sport: Liga Narodów siatkarzy/siatkarek 2026 – terminarz",
    "Interia Sport: Liga Narodów siatkarek 2026 – terminarz Polek",
]

# Times are Warsaw time as published by Polish sports outlets.
# Results are set scores from source-backed public sports reports.
RECENT_RESULTS = [
    # Men — VNL 2026, Linyi. Last three completed Poland matches as of 2026-06-15.
    {"group": "men", "date": "2026-06-14", "time": "07:00", "home": ("Polska", "pl"), "away": ("Ukraina", "ua"), "home_sets": 3, "away_sets": 2, "competition": "VNL 2026", "location": "Linyi (CHN)"},
    {"group": "men", "date": "2026-06-12", "time": "14:00", "home": ("Polska", "pl"), "away": ("Japonia", "jp"), "home_sets": 2, "away_sets": 3, "competition": "VNL 2026", "location": "Linyi (CHN)"},
    {"group": "men", "date": "2026-06-11", "time": "14:00", "home": ("Polska", "pl"), "away": ("Słowenia", "si"), "home_sets": 2, "away_sets": 3, "competition": "VNL 2026", "location": "Linyi (CHN)"},

    # Women — VNL 2026, Nanjing + Bangkok. Last three completed Poland matches as of 2026-06-17.
    {"group": "women", "date": "2026-06-17", "time": "12:00", "home": ("Polska", "pl"), "away": ("Bułgaria", "bg"), "home_sets": 3, "away_sets": 0, "competition": "VNL 2026", "location": "Bangkok (THA)"},
    {"group": "women", "date": "2026-06-07", "time": "13:00", "home": ("Polska", "pl"), "away": ("Chiny", "cn"), "home_sets": 1, "away_sets": 3, "competition": "VNL 2026", "location": "Nankin (CHN)"},
    {"group": "women", "date": "2026-06-05", "time": "13:30", "home": ("Polska", "pl"), "away": ("Serbia", "rs"), "home_sets": 3, "away_sets": 2, "competition": "VNL 2026", "location": "Nankin (CHN)"},
]

SCHEDULE = [
    # Women — VNL 2026, Bangkok + Osaka
    {"group": "women", "date": "2026-06-18", "time": "12:00", "home": ("Polska", "pl"), "away": ("Ukraina", "ua"), "competition": "VNL 2026", "location": "Bangkok (THA)"},
    {"group": "women", "date": "2026-06-20", "time": "12:00", "home": ("Polska", "pl"), "away": ("Holandia", "nl"), "competition": "VNL 2026", "location": "Bangkok (THA)"},
    {"group": "women", "date": "2026-06-21", "time": "12:00", "home": ("Polska", "pl"), "away": ("Kanada", "ca"), "competition": "VNL 2026", "location": "Bangkok (THA)"},
    {"group": "women", "date": "2026-07-08", "time": "05:00", "home": ("Polska", "pl"), "away": ("Turcja", "tr"), "competition": "VNL 2026", "location": "Osaka (JPN)"},
    {"group": "women", "date": "2026-07-09", "time": "06:00", "home": ("Polska", "pl"), "away": ("USA", "us"), "competition": "VNL 2026", "location": "Osaka (JPN)"},
    {"group": "women", "date": "2026-07-10", "time": "12:20", "home": ("Polska", "pl"), "away": ("Brazylia", "br"), "competition": "VNL 2026", "location": "Osaka (JPN)"},
    {"group": "women", "date": "2026-07-12", "time": "12:20", "home": ("Polska", "pl"), "away": ("Japonia", "jp"), "competition": "VNL 2026", "location": "Osaka (JPN)"},

    # Men — VNL 2026, Gliwice + Chicago
    {"group": "men", "date": "2026-06-24", "time": "20:00", "home": ("Polska", "pl"), "away": ("Belgia", "be"), "competition": "VNL 2026", "location": "Gliwice"},
    {"group": "men", "date": "2026-06-25", "time": "20:00", "home": ("Polska", "pl"), "away": ("Turcja", "tr"), "competition": "VNL 2026", "location": "Gliwice"},
    {"group": "men", "date": "2026-06-27", "time": "17:00", "home": ("Polska", "pl"), "away": ("Niemcy", "de"), "competition": "VNL 2026", "location": "Gliwice"},
    {"group": "men", "date": "2026-06-28", "time": "20:00", "home": ("Polska", "pl"), "away": ("Argentyna", "ar"), "competition": "VNL 2026", "location": "Gliwice"},
    {"group": "men", "date": "2026-07-15", "time": "19:00", "home": ("Polska", "pl"), "away": ("Bułgaria", "bg"), "competition": "VNL 2026", "location": "Chicago (USA)"},
    {"group": "men", "date": "2026-07-18", "time": "03:00", "home": ("Polska", "pl"), "away": ("Brazylia", "br"), "competition": "VNL 2026", "location": "Chicago (USA)"},
    {"group": "men", "date": "2026-07-18", "time": "23:00", "home": ("Polska", "pl"), "away": ("Francja", "fr"), "competition": "VNL 2026", "location": "Chicago (USA)"},
    {"group": "men", "date": "2026-07-20", "time": "03:00", "home": ("Polska", "pl"), "away": ("USA", "us"), "competition": "VNL 2026", "location": "Chicago (USA)"},
]


def dt_for(item: dict) -> datetime:
    return datetime.fromisoformat(item["date"] + "T" + item["time"] + ":00").replace(tzinfo=TZ)


def date_human(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")


def time_human(dt: datetime) -> str:
    return f"{WEEKDAYS[dt.weekday()].capitalize()}, {dt.strftime('%H:%M')}"


def team(t: tuple[str, str]) -> dict:
    return {"name": t[0], "flag": t[1]}


def match_payload(item: dict) -> dict:
    dt = dt_for(item)
    return {
        "date": item["date"],
        "date_human": date_human(dt),
        "time": time_human(dt),
        "start_at": dt.isoformat(),
        "home": team(item["home"]),
        "away": team(item["away"]),
        "competition": item["competition"],
        "location": item["location"],
        "source_mode": "curated_source_backed",
    }


def result_payload(item: dict) -> dict:
    dt = dt_for(item)
    home_sets = int(item["home_sets"])
    away_sets = int(item["away_sets"])
    return {
        "date": item["date"],
        "date_human": date_human(dt),
        "time": time_human(dt),
        "start_at": dt.isoformat(),
        "home": team(item["home"]),
        "away": team(item["away"]),
        "home_sets": home_sets,
        "away_sets": away_sets,
        "score": f"{home_sets}:{away_sets}",
        "competition": item["competition"],
        "location": item["location"],
        "source_mode": "curated_source_backed",
    }


def main() -> int:
    state_dir = resolve_state_dir(None)
    state_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TZ)
    upcoming = sorted([x for x in SCHEDULE if dt_for(x) >= now], key=dt_for)
    men = [match_payload(x) for x in upcoming if x["group"] == "men"]
    women = [match_payload(x) for x in upcoming if x["group"] == "women"]
    recent = sorted(RECENT_RESULTS, key=dt_for, reverse=True)
    recent_men = [result_payload(x) for x in recent if x["group"] == "men"][:3]
    recent_women = [result_payload(x) for x in recent if x["group"] == "women"][:3]

    volleyball = envelope(
        "volleyball",
        "ok",
        6 * 3600,
        {
            "team_label": "Polska",
            "men": men,
            "women": women,
            "recent_results": {
                "men": recent_men,
                "women": recent_women,
            },
            "source_mode": "curated_source_backed",
            "sources": SOURCES,
            "note": "Terminarz i ostatnie wyniki VNL 2026 filtrowane do widoku dashboardu; aktualizować ręcznie, gdy źródła zmienią godziny lub wyniki.",
            "last_source_review": "2026-06-17",
        },
    )
    atomic_write(state_dir / "volleyball.json", volleyball)

    print(f"wrote volleyball.json (men={len(men)}, women={len(women)}, recent_men={len(recent_men)}, recent_women={len(recent_women)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
