#!/usr/bin/env python3
"""Pure CEV EuroVolley 2026 schedule normalization.

The source boundary is deliberately narrow:
- the official CEV final-phase pages provide the currently published/current
  match cards (including concrete knockout matchups as they emerge);
- the official CEV calendar PDFs provide the complete men's pool schedule and
  the women's Poland pool fixtures.

No result or future knockout pairing is fabricated. Unknown knockout teams are
ignored until CEV publishes concrete teams on the official final-phase page.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from html import unescape
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

WARSAW_TZ = ZoneInfo("Europe/Warsaw")
UTC = timezone.utc
EDITION = 2026

SOURCES: Dict[str, Dict[str, str]] = {
    "K": {
        "id": "eurovolley-2026-women",
        "name": "CEV Trendyol EuroVolley 2026 Women",
        "official_url": "https://www-old.cev.eu/Competition-Area/competition.aspx?ID=1573&PID=2992",
        "calendar_url": "https://webmedia.cev.eu/media/ajxbenea/match-calendars-ev26w.pdf",
        "announcement_url": "https://www.cev.eu/articles/volleyball/cev-eurovolley-2026-full-competition-schedule-now-released/",
    },
    "M": {
        "id": "eurovolley-2026-men",
        "name": "CEV Enel EuroVolley 2026 Men",
        "official_url": "https://www-old.cev.eu/Competition-Area/competition.aspx?ID=1572&PID=2990",
        "calendar_url": "https://webmedia.cev.eu/media/slmjk2cz/match-calendars-ev26m.pdf",
        "announcement_url": "https://www.cev.eu/articles/volleyball/cev-eurovolley-2026-full-competition-schedule-now-released/",
    },
}

# CEV uses uppercase source labels. The display name is kept separate so the
# dashboard can use readable Polish labels without losing the source literal.
TEAM_CODES: Dict[str, str] = {
    "ALBANIA": "ALB",
    "AUSTRIA": "AUT",
    "AZERBAIJAN": "AZE",
    "BELGIUM": "BEL",
    "BOSNIA AND HERZEGOVINA": "BIH",
    "BULGARIA": "BUL",
    "CROATIA": "CRO",
    "CZECHIA": "CZE",
    "DENMARK": "DEN",
    "ESTONIA": "EST",
    "FINLAND": "FIN",
    "FRANCE": "FRA",
    "GEORGIA": "GEO",
    "GERMANY": "GER",
    "GREAT BRITAIN": "GBR",
    "GREECE": "GRE",
    "HUNGARY": "HUN",
    "ISRAEL": "ISR",
    "ITALY": "ITA",
    "KOSOVO": "KOS",
    "LATVIA": "LAT",
    "MOLDOVA": "MDA",
    "MONTENEGRO": "MNE",
    "NETHERLANDS": "NED",
    "NORTH MACEDONIA": "MKD",
    "NORWAY": "NOR",
    "POLAND": "POL",
    "PORTUGAL": "POR",
    "ROMANIA": "ROU",
    "SERBIA": "SRB",
    "SLOVAKIA": "SVK",
    "SLOVENIA": "SLO",
    "SPAIN": "ESP",
    "SWEDEN": "SWE",
    "SWITZERLAND": "SUI",
    "THE NETHERLANDS": "NED",
    "TÜRKIYE": "TUR",
    "TURKIYE": "TUR",
    "TURKEY": "TUR",
    "UKRAINE": "UKR",
}

TEAM_LABELS: Dict[str, str] = {
    "POL": "Polska",
    "HUN": "Węgry",
    "LAT": "Łotwa",
    "SLO": "Słowenia",
    "GER": "Niemcy",
    "TUR": "Türkiye",
    "POR": "Portugalia",
    "ISR": "Izrael",
    "MKD": "Macedonia Północna",
    "UKR": "Ukraina",
    "BUL": "Bułgaria",
    "ITA": "Włochy",
    "SWE": "Szwecja",
    "CZE": "Czechy",
    "GRE": "Grecja",
    "SVK": "Słowacja",
    "ESP": "Hiszpania",
    "BEL": "Belgia",
    "AUT": "Austria",
    "ROU": "Rumunia",
    "NED": "Niderlandy",
    "FIN": "Finlandia",
    "DEN": "Dania",
    "NOR": "Norwegia",
    "MNE": "Czarnogóra",
    "SRB": "Serbia",
    "CRO": "Chorwacja",
    "SUI": "Szwajcaria",
}

# Group stages are the only static rows retained in this module. These exact
# local dates/times are transcribed from the official CEV calendar PDFs above.
# The source-local timezone is converted to a real UTC instant below.
POLAND_POOL_ROWS: Sequence[Mapping[str, str]] = (
    # Women, Pool A — Istanbul (Türkiye), official local time.
    {"gender": "K", "pool": "A", "date": "2026-08-22", "time": "19:00", "home": "HUNGARY", "away": "POLAND", "city": "Istanbul", "country": "Türkiye", "tz": "Europe/Istanbul"},
    {"gender": "K", "pool": "A", "date": "2026-08-24", "time": "16:00", "home": "POLAND", "away": "LATVIA", "city": "Istanbul", "country": "Türkiye", "tz": "Europe/Istanbul"},
    {"gender": "K", "pool": "A", "date": "2026-08-25", "time": "19:00", "home": "POLAND", "away": "SLOVENIA", "city": "Istanbul", "country": "Türkiye", "tz": "Europe/Istanbul"},
    {"gender": "K", "pool": "A", "date": "2026-08-27", "time": "16:00", "home": "POLAND", "away": "GERMANY", "city": "Istanbul", "country": "Türkiye", "tz": "Europe/Istanbul"},
    {"gender": "K", "pool": "A", "date": "2026-08-28", "time": "19:00", "home": "TÜRKIYE", "away": "POLAND", "city": "Istanbul", "country": "Türkiye", "tz": "Europe/Istanbul"},
    # Men, Pool B — Sofia (Bulgaria), official local time.
    {"gender": "M", "pool": "B", "date": "2026-09-10", "time": "16:00", "home": "POLAND", "away": "PORTUGAL", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-12", "time": "16:00", "home": "POLAND", "away": "ISRAEL", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-13", "time": "19:00", "home": "NORTH MACEDONIA", "away": "POLAND", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-15", "time": "19:00", "home": "POLAND", "away": "UKRAINE", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-16", "time": "19:00", "home": "POLAND", "away": "BULGARIA", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
)

# Men's complete group-stage calendar from the official CEV PDF. The five
# Poland rows intentionally overlap POLAND_POOL_ROWS; static_schedule_matches
# de-duplicates them while static_poland_matches keeps its stable 10-row API.
MEN_POOL_ROWS: Sequence[Mapping[str, str]] = (
    # Pool A — Naples/Modena (Italy), official local time.
    {"gender": "M", "pool": "A", "date": "2026-09-10", "time": "21:05", "home": "ITALY", "away": "SWEDEN", "city": "Naples", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-11", "time": "16:00", "home": "CZECHIA", "away": "GREECE", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-11", "time": "21:00", "home": "SLOVAKIA", "away": "SLOVENIA", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-12", "time": "16:00", "home": "SWEDEN", "away": "CZECHIA", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-12", "time": "21:05", "home": "GREECE", "away": "ITALY", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-13", "time": "16:00", "home": "SLOVENIA", "away": "SWEDEN", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-13", "time": "21:05", "home": "ITALY", "away": "SLOVAKIA", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-14", "time": "16:00", "home": "SLOVAKIA", "away": "CZECHIA", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-14", "time": "21:00", "home": "SLOVENIA", "away": "GREECE", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-15", "time": "16:00", "home": "GREECE", "away": "SWEDEN", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-15", "time": "21:05", "home": "CZECHIA", "away": "ITALY", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-16", "time": "16:00", "home": "SWEDEN", "away": "SLOVAKIA", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-16", "time": "21:05", "home": "CZECHIA", "away": "SLOVENIA", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-17", "time": "16:00", "home": "SLOVAKIA", "away": "GREECE", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},
    {"gender": "M", "pool": "A", "date": "2026-09-17", "time": "21:05", "home": "ITALY", "away": "SLOVENIA", "city": "Modena", "country": "Italy", "tz": "Europe/Rome"},

    # Pool B — Sofia (Bulgaria), official local time.
    {"gender": "M", "pool": "B", "date": "2026-09-09", "time": "19:00", "home": "BULGARIA", "away": "NORTH MACEDONIA", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-10", "time": "16:00", "home": "POLAND", "away": "PORTUGAL", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-10", "time": "19:00", "home": "ISRAEL", "away": "UKRAINE", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-11", "time": "16:00", "home": "UKRAINE", "away": "NORTH MACEDONIA", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-11", "time": "19:00", "home": "PORTUGAL", "away": "BULGARIA", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-12", "time": "16:00", "home": "POLAND", "away": "ISRAEL", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-12", "time": "19:00", "home": "BULGARIA", "away": "UKRAINE", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-13", "time": "16:00", "home": "PORTUGAL", "away": "ISRAEL", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-13", "time": "19:00", "home": "NORTH MACEDONIA", "away": "POLAND", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-14", "time": "16:00", "home": "UKRAINE", "away": "PORTUGAL", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-14", "time": "19:00", "home": "BULGARIA", "away": "ISRAEL", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-15", "time": "16:00", "home": "NORTH MACEDONIA", "away": "PORTUGAL", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-15", "time": "19:00", "home": "POLAND", "away": "UKRAINE", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-16", "time": "16:00", "home": "ISRAEL", "away": "NORTH MACEDONIA", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},
    {"gender": "M", "pool": "B", "date": "2026-09-16", "time": "19:00", "home": "POLAND", "away": "BULGARIA", "city": "Sofia", "country": "Bulgaria", "tz": "Europe/Sofia"},

    # Pool C — Tampere (Finland), official local time.
    {"gender": "M", "pool": "C", "date": "2026-09-10", "time": "20:00", "home": "FINLAND", "away": "DENMARK", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-11", "time": "17:00", "home": "NETHERLANDS", "away": "BELGIUM", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-11", "time": "20:00", "home": "SERBIA", "away": "ESTONIA", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-12", "time": "15:00", "home": "DENMARK", "away": "NETHERLANDS", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-12", "time": "18:00", "home": "BELGIUM", "away": "FINLAND", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-13", "time": "15:00", "home": "ESTONIA", "away": "DENMARK", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-13", "time": "18:00", "home": "FINLAND", "away": "SERBIA", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-14", "time": "17:00", "home": "SERBIA", "away": "NETHERLANDS", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-14", "time": "20:00", "home": "ESTONIA", "away": "BELGIUM", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-15", "time": "17:00", "home": "BELGIUM", "away": "DENMARK", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-15", "time": "20:00", "home": "NETHERLANDS", "away": "FINLAND", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-16", "time": "17:00", "home": "DENMARK", "away": "SERBIA", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-16", "time": "20:00", "home": "NETHERLANDS", "away": "ESTONIA", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-17", "time": "17:00", "home": "SERBIA", "away": "BELGIUM", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},
    {"gender": "M", "pool": "C", "date": "2026-09-17", "time": "20:00", "home": "FINLAND", "away": "ESTONIA", "city": "Tampere", "country": "Finland", "tz": "Europe/Helsinki"},

    # Pool D — Cluj-Napoca (Romania), official local time.
    {"gender": "M", "pool": "D", "date": "2026-09-09", "time": "20:00", "home": "ROMANIA", "away": "LATVIA", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-10", "time": "17:00", "home": "FRANCE", "away": "SWITZERLAND", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-10", "time": "20:00", "home": "TÜRKIYE", "away": "GERMANY", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-11", "time": "17:00", "home": "GERMANY", "away": "LATVIA", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-11", "time": "20:00", "home": "SWITZERLAND", "away": "ROMANIA", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-12", "time": "17:00", "home": "FRANCE", "away": "TÜRKIYE", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-12", "time": "20:00", "home": "ROMANIA", "away": "GERMANY", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-13", "time": "17:00", "home": "SWITZERLAND", "away": "TÜRKIYE", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-13", "time": "20:00", "home": "LATVIA", "away": "FRANCE", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-14", "time": "17:00", "home": "GERMANY", "away": "SWITZERLAND", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-14", "time": "20:00", "home": "ROMANIA", "away": "TÜRKIYE", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-15", "time": "17:00", "home": "LATVIA", "away": "SWITZERLAND", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-15", "time": "20:00", "home": "FRANCE", "away": "GERMANY", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-16", "time": "17:00", "home": "TÜRKIYE", "away": "LATVIA", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
    {"gender": "M", "pool": "D", "date": "2026-09-16", "time": "20:00", "home": "FRANCE", "away": "ROMANIA", "city": "Cluj-Napoca", "country": "Romania", "tz": "Europe/Bucharest"},
)

# The final-phase pages expose one current leg per phase. The group indices
# are stable in the official CEV legacy page as of the 2026 competition.
PHASE_BY_GROUP: Dict[str, Dict[int, Tuple[str, str]]] = {
    "K": {
        0: ("Faza grupowa", "Grupa A"), 1: ("Faza grupowa", "Grupa B"),
        2: ("Faza grupowa", "Grupa C"), 3: ("Faza grupowa", "Grupa D"),
        4: ("1/8 finału", "Faza finałowa"), 5: ("1/8 finału", "Faza finałowa"),
        6: ("Ćwierćfinał", "Faza finałowa"), 7: ("Ćwierćfinał", "Faza finałowa"),
        8: ("Półfinał", "Faza finałowa"), 9: ("Mecz o 3. miejsce", "Faza finałowa"),
        10: ("Finał", "Faza finałowa"),
    },
    "M": {
        0: ("Faza grupowa", "Grupa A"), 1: ("Faza grupowa", "Grupa B"),
        2: ("Faza grupowa", "Grupa C"), 3: ("Faza grupowa", "Grupa D"),
        4: ("1/8 finału", "Faza finałowa"), 5: ("1/8 finału", "Faza finałowa"),
        6: ("Ćwierćfinał", "Faza finałowa"), 7: ("Ćwierćfinał", "Faza finałowa"),
        8: ("Półfinał", "Faza finałowa"), 9: ("Mecz o 3. miejsce", "Faza finałowa"),
        10: ("Finał", "Faza finałowa"),
    },
}

VENUES: Dict[str, Dict[int, Dict[str, Optional[str]]]] = {
    "K": {
        0: {"city": "Istanbul", "country": "Türkiye", "timezone": "Europe/Istanbul"},
        1: {"city": "Brno", "country": "Czechia", "timezone": "Europe/Prague"},
        2: {"city": "Baku", "country": "Azerbaijan", "timezone": "Asia/Baku"},
        3: {"city": "Gothenburg", "country": "Sweden", "timezone": "Europe/Stockholm"},
        4: {"city": "Brno", "country": "Czechia", "timezone": "Europe/Prague"},
        5: {"city": "Istanbul", "country": "Türkiye", "timezone": "Europe/Istanbul"},
        6: {"city": "Brno", "country": "Czechia", "timezone": "Europe/Prague"},
        7: {"city": "Istanbul", "country": "Türkiye", "timezone": "Europe/Istanbul"},
        8: {"city": "Istanbul", "country": "Türkiye", "timezone": "Europe/Istanbul"},
        9: {"city": "Istanbul", "country": "Türkiye", "timezone": "Europe/Istanbul"},
        10: {"city": "Istanbul", "country": "Türkiye", "timezone": "Europe/Istanbul"},
    },
    "M": {
        0: {"city": None, "country": "Italy", "timezone": "Europe/Rome"},
        1: {"city": "Sofia", "country": "Bulgaria", "timezone": "Europe/Sofia"},
        2: {"city": "Tampere", "country": "Finland", "timezone": "Europe/Helsinki"},
        3: {"city": "Cluj-Napoca", "country": "Romania", "timezone": "Europe/Bucharest"},
        4: {"city": "Bulgaria", "country": "Bulgaria", "timezone": "Europe/Sofia"},
        5: {"city": "Italy", "country": "Italy", "timezone": "Europe/Rome"},
        6: {"city": "Bulgaria", "country": "Bulgaria", "timezone": "Europe/Sofia"},
        7: {"city": "Italy", "country": "Italy", "timezone": "Europe/Rome"},
        8: {"city": "Italy", "country": "Italy", "timezone": "Europe/Rome"},
        9: {"city": "Italy", "country": "Italy", "timezone": "Europe/Rome"},
        10: {"city": "Italy", "country": "Italy", "timezone": "Europe/Rome"},
    },
}


def _clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]*>", " ", raw or "")
    text = unescape(text).replace("\xa0", " ")
    return " ".join(text.split()).strip()


def _team_code(source_name: str) -> str:
    key = _clean_text(source_name).upper()
    return TEAM_CODES.get(key, re.sub(r"[^A-Z]", "", key)[:3] or "UNK")


def _team(source_name: str) -> Dict[str, str]:
    code = _team_code(source_name)
    return {
        "code": code,
        "name": TEAM_LABELS.get(code, _clean_text(source_name).title()),
        "source_name": _clean_text(source_name),
        "flag": code.lower(),
    }


def _parse_date(value: str, year: int = EDITION) -> date:
    value = _clean_text(value)
    parts = value.split("/")
    if len(parts) not in (2, 3):
        raise ValueError(f"invalid CEV date: {value!r}")
    parsed_year = year if len(parts) == 2 else int(parts[2])
    return date(parsed_year, int(parts[1]), int(parts[0]))


def _parse_time(value: str) -> time:
    value = _clean_text(value)
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _match(
    *, gender: str, source_id: str, home: str, away: str, source_date: date,
    source_time: time, venue: Mapping[str, Optional[str]], phase: str,
    round_name: str, source_url: str, retrieved_at: str,
    status: str = "scheduled", score: Optional[str] = None,
) -> Dict[str, Any]:
    tz_name = venue.get("timezone") or "Europe/Warsaw"
    local_dt = datetime.combine(source_date, source_time, tzinfo=ZoneInfo(tz_name))
    utc_dt = local_dt.astimezone(UTC)
    warsaw_dt = utc_dt.astimezone(WARSAW_TZ)
    competition = SOURCES[gender]
    return {
        "id": f"{gender}-{source_id}",
        "official_code": source_id,
        "competition_id": competition["id"],
        "competition": competition["name"],
        "gender": gender,
        "gender_label": "kobiety" if gender == "K" else "mężczyźni",
        "edition": EDITION,
        "phase": phase,
        "round": round_name,
        "status": status,
        "score": score,
        "home": _team(home),
        "away": _team(away),
        "source_date": source_date.isoformat(),
        "source_time": source_time.strftime("%H:%M"),
        "start_at": _iso(utc_dt),
        "warsaw_date": warsaw_dt.date().isoformat(),
        "warsaw_time": warsaw_dt.strftime("%H:%M"),
        "timezone": "Europe/Warsaw",
        "venue": {
            "city": venue.get("city"),
            "country": venue.get("country"),
            "timezone": tz_name,
        },
        "source": {
            "url": source_url,
            "retrieved_at": retrieved_at,
            "kind": "official-cev",
        },
    }


def _rows_to_matches(rows: Iterable[Mapping[str, str]], retrieved_at: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for row in rows:
        gender = row["gender"]
        competition = SOURCES[gender]
        source_date = date.fromisoformat(row["date"])
        source_time = _parse_time(row["time"])
        source_id = f"calendar-{gender}-{row['date']}-{_team_code(row['home'])}-{_team_code(row['away'])}"
        matches.append(
            _match(
                gender=gender,
                source_id=source_id,
                home=row["home"],
                away=row["away"],
                source_date=source_date,
                source_time=source_time,
                venue={"city": row["city"], "country": row["country"], "timezone": row["tz"]},
                phase="Faza grupowa",
                round_name=f"Grupa {row['pool']}",
                source_url=competition["calendar_url"],
                retrieved_at=retrieved_at,
            )
        )
    return matches


def static_poland_matches(retrieved_at: str) -> List[Dict[str, Any]]:
    """Return the stable Poland-only calendar used by UL and the ticker."""
    return _rows_to_matches(POLAND_POOL_ROWS, retrieved_at)


def static_schedule_matches(retrieved_at: str) -> List[Dict[str, Any]]:
    """Return every statically known daily pool fixture for the LL day view."""
    poland_keys = {
        (row["date"], _team_code(row["home"]), _team_code(row["away"]))
        for row in POLAND_POOL_ROWS
    }
    rows: List[Mapping[str, str]] = list(POLAND_POOL_ROWS)
    rows.extend(
        row for row in MEN_POOL_ROWS
        if (row["date"], _team_code(row["home"]), _team_code(row["away"])) not in poland_keys
    )
    return _rows_to_matches(rows, retrieved_at)


def _field(html: str, base: str, suffix: str) -> str:
    pattern = re.compile(
        r"<(?:span|a|div)\b[^>]*\bid=[\"']"
        + re.escape(base + "_" + suffix)
        + r"[\"'][^>]*>(.*?)</(?:span|a|div)>",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(html)
    return _clean_text(match.group(1)) if match else ""


def _match_page_url(html: str, start: int) -> str:
    """Return a concrete official CEV MatchPage URL near a card.

    The final-phase list occasionally leaves ``LB_Data``/``Label1`` empty
    after a knockout card becomes concrete. The linked MatchPage still has
    the authoritative date and time, so the refresh probe may resolve it.
    """
    window_start = max(0, start - 6000)
    window = html[window_start : start + 6000]
    match_pattern = re.compile(
        r"MatchPage\.aspx\?(?:ID=\d+(?:&amp;|&)mID=\d+|"
        r"mID=\d+(?:&amp;|&)ID=\d+)",
        re.IGNORECASE,
    )
    match = next(match_pattern.finditer(window), None)
    if not match:
        return ""
    quote_start = max(window.rfind('"', 0, match.start()), window.rfind("'", 0, match.start()))
    href = unescape(window[quote_start + 1 : match.end()])
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return "https://www-old.cev.eu" + href
    return "https://www-old.cev.eu/Competition-Area/" + href.lstrip("~/")


def _detail_field(html: str, suffix: str) -> str:
    """Read a labelled value from an official CEV MatchPage."""
    pattern = re.compile(
        r"<(?:span|div)\b[^>]*\bid=[\"'][^\"']*_"
        + re.escape(suffix)
        + r"[\"'][^>]*>(.*?)</(?:span|div)>",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(html)
    return _clean_text(match.group(1)) if match else ""


def _is_placeholder(name: str) -> bool:
    value = _clean_text(name).upper()
    return not value or value in {"TBD", "T.B.D.", "?"} or "WINNER" in value or "LOSER" in value


def parse_cev_final_page(
    html: str,
    gender: str,
    retrieved_at: str,
    detail_fetch: Optional[Callable[[str], str]] = None,
) -> List[Dict[str, Any]]:
    """Parse concrete match cards from one official CEV final-phase page.

    The legacy page uses stable field suffixes (`LB_FMN`, `LB_Home`,
    `LB_Guest`, `LB_Data`, `Label1`, `Label3`, `LB_VintiOspiti`). We key off
    those semantic suffixes rather than coupling to the changing outer ASP.NET
    control prefix.
    """
    matches: List[Dict[str, Any]] = []
    code_pattern = re.compile(
        r"<(?P<tag>span|a)\b[^>]*\bid=[\"'](?P<id>[^\"']*"
        r"RADLIST_Championship_ctrl(?P<group>\d+)_RADLIST_Leg_ctrl\d+_"
        r"RADLIST_Matches_ctrl(?P<match>\d+)_LB_FMN)[\"'][^>]*>"
        r"(?P<body>.*?)</(?P=tag)>",
        re.IGNORECASE | re.DOTALL,
    )
    for card in code_pattern.finditer(html):
        source_id = _clean_text(card.group("body"))
        group = int(card.group("group"))
        base = card.group("id")[: -len("_LB_FMN")]
        home = _field(html, base, "LB_Home")
        away = _field(html, base, "LB_Guest")
        date_text = _field(html, base, "LB_Data")
        time_text = _field(html, base, "Label1")
        if _is_placeholder(home) or _is_placeholder(away):
            # CEV publishes bracket placeholders before teams are known. They
            # are not match data and must not appear as guessed fixtures.
            continue
        if (not date_text or not time_text) and detail_fetch:
            match_url = _match_page_url(html, card.end())
            if match_url:
                try:
                    detail_html = detail_fetch(match_url)
                except Exception:
                    detail_html = ""
                date_text = date_text or _detail_field(detail_html, "L_MatchDate")
                time_text = time_text or _detail_field(detail_html, "L_MatchHour")
        if not date_text or not time_text:
            continue
        try:
            source_date = _parse_date(date_text)
            source_time = _parse_time(time_text)
        except (ValueError, TypeError):
            continue
        home_score = _field(html, base, "Label3")
        away_score = _field(html, base, "LB_VintiOspiti")
        score = None
        status = "scheduled"
        if home_score.isdigit() and away_score.isdigit():
            score = f"{home_score}:{away_score}"
            status = "finished"
        phase, round_name = PHASE_BY_GROUP.get(gender, {}).get(
            group, ("Faza finałowa", "Oficjalny terminarz CEV")
        )
        matches.append(
            _match(
                gender=gender,
                source_id=source_id,
                home=home,
                away=away,
                source_date=source_date,
                source_time=source_time,
                venue=VENUES[gender].get(group, {"city": None, "country": None, "timezone": "Europe/Warsaw"}),
                phase=phase,
                round_name=round_name,
                source_url=SOURCES[gender]["official_url"],
                retrieved_at=retrieved_at,
                status=status,
                score=score,
            )
        )
    return matches


# Public ASCII parser name used by the refresh probe and tests.


def _merge_key(match: Mapping[str, Any]) -> Tuple[Any, ...]:
    home = match.get("home") or {}
    away = match.get("away") or {}
    return (
        match.get("gender"), match.get("source_date"),
        home.get("code"), away.get("code"), match.get("phase"),
    )


def merge_matches(static_matches: Iterable[Mapping[str, Any]], dynamic_matches: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for match in static_matches:
        merged[_merge_key(match)] = dict(match)
    for match in dynamic_matches:
        key = _merge_key(match)
        # Concrete official CEV cards override the PDF schedule row with live
        # status/score while preserving the normalized shape.
        merged[key] = dict(match)
    return sorted(merged.values(), key=lambda item: (item.get("start_at") or "", item.get("gender") or "", item.get("id") or ""))


def _group_days(matches: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for match in matches:
        day = match.get("warsaw_date")
        if not day:
            continue
        by_day.setdefault(str(day), []).append(dict(match))
    days = []
    for day in sorted(by_day):
        rows = sorted(by_day[day], key=lambda item: (item.get("warsaw_time") or "99:99", item.get("gender") or "", item.get("id") or ""))
        days.append({"date": day, "matches": rows})
    return days


def build_data(dynamic_matches: Iterable[Mapping[str, Any]], retrieved_at: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    dynamic = [dict(m) for m in dynamic_matches]
    # LL is the day view, so it must see the complete official men's pool
    # calendar, not only Poland's rows. Dynamic CEV cards still win when the
    # official page publishes a result/status update for a static fixture.
    all_matches = merge_matches(static_schedule_matches(retrieved_at), dynamic)
    poland = [
        m for m in all_matches
        if "POL" in {((m.get("home") or {}).get("code")), ((m.get("away") or {}).get("code"))}
    ]
    current_day = (now or datetime.now(WARSAW_TZ)).astimezone(WARSAW_TZ).date().isoformat()
    competitions = []
    for gender in ("K", "M"):
        comp = SOURCES[gender]
        comp_matches = [m for m in all_matches if m.get("gender") == gender]
        competitions.append({
            "id": comp["id"],
            "name": comp["name"],
            "gender": gender,
            "gender_label": "kobiety" if gender == "K" else "mężczyźni",
            "edition": EDITION,
            "official_url": comp["official_url"],
            "calendar_url": comp["calendar_url"],
            "match_count": len(comp_matches),
            "matches": comp_matches,
        })
    return {
        "schema_version": 1,
        "kind": "eurovolley_schedule",
        "edition": EDITION,
        "timezone": "Europe/Warsaw",
        "selected_date": current_day,
        "matches": all_matches,
        "days": _group_days(all_matches),
        "poland_matches": poland,
        "competitions": competitions,
        "official_sources": [
            {"gender": gender, "name": SOURCES[gender]["name"], "url": SOURCES[gender]["official_url"], "calendar_url": SOURCES[gender]["calendar_url"]}
            for gender in ("K", "M")
        ],
        "freshness": {
            "refresh_status": "live",
            "retrieved_at": retrieved_at,
            "last_success_at": retrieved_at,
            "source_match_count": len(all_matches),
            "poland_match_count": len(poland),
        },
        "coverage": {
            "daily": "official CEV final-phase pages plus the complete men's pool calendar and planned women's Poland fixtures from the official calendar PDFs",
            "poland": "official CEV 2026 calendar PDFs plus concrete final-phase cards",
            "tbd_policy": "CEV bracket placeholders are omitted until both teams are published",
        },
    }


def empty_data(retrieved_at: str) -> Dict[str, Any]:
    return build_data([], retrieved_at)
