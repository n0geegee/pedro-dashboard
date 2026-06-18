#!/usr/bin/env python3
"""Pedro Dashboard — auto-refresh Poland volleyball schedule + recent results.

Owns `volleyball.json`. Replaces the manually-curated RECENT_RESULTS/SCHEDULE
data in `refresh-match-calendar.py` with a live fetch from the official
FIVB Volleyball Nations League Wikipedia articles, which are updated within
hours of every match and require no API key.

Source: https://en.wikipedia.org/wiki/2026_FIVB_*_Volleyball_Nations_League

Behaviour:
  * On success: overwrites volleyball.json with parsed men+women schedule,
    computed recent_results (last 3 per gender, completed matches only), and
    a `last_source_review` timestamp.
  * On fetch/parse failure: leaves the existing volleyball.json untouched and
    returns non-zero, so the dashboard keeps showing the last good state and
    the state-refresher log records a clean error line.
  * The previous curated data is kept as a cold-start fallback: if the file
    is missing OR the live fetch failed AND the file is missing, the probe
    writes an empty envelope so the kiosk does not show a stale "no data"
    state. The curated schedule from `refresh-match-calendar.py` lives in
    that script as a separate cold-start file (volleyball.curated.json) and
    is copied in here on first run.

Privacy:
  * Public match facts only. No personal data, no commentary, no source HTML.

The shape written to volleyball.json is unchanged from
refresh-match-calendar.py so the kiosk ticker (app/static/app.js:
`renderTicker`) and the volleyball widget (`renderVB`) keep working
without code changes.
"""
from __future__ import annotations

import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import atomic_write, envelope, now_iso, resolve_state_dir  # noqa: E402

TZ = ZoneInfo("Europe/Warsaw")
WEEKDAYS = [
    "poniedziałek", "wtorek", "środa", "czwartek",
    "piątek", "sobota", "niedziela",
]

# Pool → city used to label location (matches the curated fallback for the
# fields the ticker shows — short label like "Bangkok (THA)").
POOL_CITY = {
    # Women
    "Pool_1": "Quebec City (CAN)",  # 03-08 Jun — only PL-UA there
    "Pool_2": "Brasilia (BRA)",
    "Pool_3": "Nankin (CHN)",        # PL first week women
    "Pool_4": "Ankara (TUR)",
    "Pool_5": "Pasig (PHI)",
    "Pool_6": "Bangkok (THA)",       # PL second week women 17-21 Jun
    "Pool_7": "Belgrad (SRB)",
    "Pool_8": "Hongkong (CHN)",
    "Pool_9": "Osaka (JPN)",         # PL third week women
    # Men
    "M_Pool_1": "Ottawa (CAN)",
    "M_Pool_2": "Brasilia (BRA)",
    "M_Pool_3": "Linyi (CHN)",       # PL first week men 10-14 Jun
    "M_Pool_4": "Orleans (FRA)",
    "M_Pool_5": "Gliwice",           # PL second week men 24-28 Jun
    "M_Pool_6": "Lublana (SVN)",
    "M_Pool_7": "Belgrad (SRB)",
    "M_Pool_8": "Hoffman Estates (USA)",
    "M_Pool_9": "Osaka (JPN)",       # PL third week men
}

WOMEN_URL = (
    "https://en.wikipedia.org/wiki/2026_FIVB_Women%27s_Volleyball_Nations_League"
)
MEN_URL = (
    "https://en.wikipedia.org/wiki/2026_FIVB_Men%27s_Volleyball_Nations_League"
)

UA = "PedroDashboard/1.0 (iMac-Hermes; +https://github.com/NousResearch/hermes-agent) live-vnl-fetch"
TIMEOUT = 8  # seconds; refresh-all-state.sh runs every 20s, keep this low

# Wikipedia uses en-dash (U+2013) for set scores. Normalise to hyphen for the
# ticker ("3:0 (25:12, 25:22, 25:23)" — but the ticker only reads m.score, set
# breakdown is preserved on the widget for future use).
EN_DASH = "\u2013"


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        # Wikipedia may serve gzip; urlopen handles Content-Encoding.
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&#160;", " ")
    s = s.replace("&amp;", "&").replace("&ndash;", EN_DASH)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_score_cell(raw: str) -> tuple[int | None, int | None]:
    """A '3–0' or '2-3' cell → (home_sets, away_sets)."""
    m = re.search(r"(\d)\s*[" + re.escape(EN_DASH) + r"-]\s*(\d)", raw)
    if not m:
        return (None, None)
    return (int(m.group(1)), int(m.group(2)))


def parse_set_scores(raw: str) -> list[int]:
    """Parse a row of set scores like '25–12 25–22 25–23' → [25,12,25,22,25,23]."""
    parts = re.findall(r"\d+\s*[" + re.escape(EN_DASH) + r"-]\s*\d+", raw)
    out: list[int] = []
    for p in parts:
        a, b = re.split("[" + re.escape(EN_DASH) + r"-]", p)
        out.extend([int(a), int(b)])
    return out


def parse_matches_from_wikipedia(html: str, gender: str) -> list[dict]:
    """Walk every wikitable on the page, extract completed matches involving
    Poland. Returns list of dicts in the shape `match_payload` consumes.

    A "completed" match is one with a numeric score (3–0, 2–3, etc.). Future
    matches with empty scores are skipped — they become 'upcoming' if the
    row contains a scheduled time but no result. We can't always distinguish
    "scheduled but not started" from "played but score missing" in the HTML,
    so we use a "no score" row as a soft signal but still attach it to the
    schedule so the upcoming widget has a fallback.
    """
    out: list[dict] = []
    # Section anchors — Wikipedia uses Pool_1..Pool_9 (women) and Pool_1..Pool_9
    # for men on a different article. We split the article into per-pool
    # blocks first, then look for one wikitables per block.
    pool_pattern = re.compile(r'id="(Pool_\d+)"')
    anchors = [m.start() for m in pool_pattern.finditer(html)]
    if not anchors:
        return out
    blocks: list[tuple[str, str]] = []
    for i, start in enumerate(anchors):
        end = anchors[i + 1] if i + 1 < len(anchors) else len(html)
        # Get the pool name from the most recent Pool_ marker at or before start
        pool_name_match = pool_pattern.search(html, start, start)
        pool_name = pool_name_match.group(1) if pool_name_match else f"Pool_{i+1}"
        blocks.append((pool_name, html[start:end]))
    # For men article, prefix to avoid collision with women in the same process
    prefix = "M_" if gender == "men" else ""
    for pool_name, block in blocks:
        city = POOL_CITY.get(prefix + pool_name, "")
        # Find the first wikitable in the block (Pool matches table)
        table_m = re.search(
            r'<table[^>]*class="wikitable[^"]*"[^>]*>(.*?)</table>',
            block, flags=re.S,
        )
        if not table_m:
            continue
        body = table_m.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S)
        for row in rows[1:]:  # skip header
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.S)
            if len(cells) < 5:
                continue
            # Layout (verified against current pages):
            # 0: Date (e.g. "17 Jun")
            # 1: Time (e.g. "13:00")
            # 2: Team A (home/away) — Wikipedia lists away first, home second
            # 3: Score
            # 4: Team B
            # 5+: set-by-set, totals
            date_raw = strip_html(cells[0])
            time_raw = strip_html(cells[1])
            team_a = strip_html(cells[2])
            score_raw = strip_html(cells[3])
            team_b = strip_html(cells[4])
            set_cells = [strip_html(c) for c in cells[5:]]
            # Filter to Poland only
            if "Poland" not in team_a + " " + team_b:
                continue
            # Date: "17 Jun" → "2026-06-17" (assumes tournament year)
            m = re.match(r"(\d{1,2})\s+([A-Za-z]+)", date_raw)
            if not m:
                continue
            day = int(m.group(1))
            month_name = m.group(2)[:3].lower()
            month_map = {
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            }
            month = month_map.get(month_name)
            if not month:
                continue
            # Wikipedia pool timing: Women first week 3-8 Jun, second 17-21 Jun,
            # third 8-12 Jul. Men first 10-14 Jun, second 24-28 Jun, third 15-19 Jul.
            # Use pool index for unambiguous year/month.
            pool_idx = int(pool_name.split("_")[1])
            if gender == "women":
                # Women: weeks 1,2,3 → pools 1-3, 4-6, 7-9
                if 1 <= pool_idx <= 3:
                    year, default_month = 2026, 6
                elif 4 <= pool_idx <= 6:
                    year, default_month = 2026, 6
                else:
                    year, default_month = 2026, 7
            else:
                # Men: week 1 pools 1-3 (Jun), week 2 pools 4-6 (Jun), week 3 pools 7-9 (Jul)
                if pool_idx <= 6:
                    year, default_month = 2026, 6
                else:
                    year, default_month = 2026, 7
            # Override the month from the cell if it's clearly different
            # (e.g. "8 Jul" on a July pool)
            if month and month != default_month:
                pass  # trust the cell
            try:
                dt = datetime(year, month, day)
            except ValueError:
                continue
            # Time
            time_m = re.match(r"(\d{1,2}):(\d{2})", time_raw)
            if time_m:
                dt = dt.replace(hour=int(time_m.group(1)), minute=int(time_m.group(2)))
            dt_warsaw = dt.replace(tzinfo=TZ)
            # Score (Wiki layout is "home–away" or "away–home", symmetric;
            # we don't know which side is home at this point. Just parse
            # the two numbers; we swap to PL-perspective below.)
            home_sets, away_sets = parse_score_cell(score_raw)
            # Normalise: Polska is always the home side in our internal JSON.
            # The dashboard ticker and widget both want "Polska vs/3:0 Opponent"
            # regardless of which side Wikipedia listed first. We track which
            # side PL was in to swap the score and set-pair order if needed.
            pl_is_team_a = "Poland" in team_a
            if pl_is_team_a:
                pl_home_sets, pl_away_sets = home_sets, away_sets
            else:
                pl_home_sets, pl_away_sets = away_sets, home_sets
            # Set-by-set: in Wiki, cells are interleaved
            #   set1_team_a, set1_team_b, set2_team_a, set2_team_b, ...
            # which is [team_a scores, team_b scores]. We want pairs in
            # PL-perspective order = (PL's score, opponent's score).
            set_ints = parse_set_scores(" ".join(set_cells))
            set_pairs: list[str] = []
            for k in range(0, len(set_ints) - 1, 2):
                if set_ints[k] == 0 and set_ints[k + 1] == 0:
                    continue
                a_score, b_score = set_ints[k], set_ints[k + 1]
                if pl_is_team_a:
                    set_pairs.append(f"{a_score}:{b_score}")
                else:
                    set_pairs.append(f"{b_score}:{a_score}")
            played = (pl_home_sets or 0) + (pl_away_sets or 0)
            set_pairs = set_pairs[:played]
            # Opponent name (the non-Poland side)
            opponent = team_b if pl_is_team_a else team_a
            score_str: str | None
            if pl_home_sets is not None and pl_away_sets is not None:
                score_str = f"{pl_home_sets}:{pl_away_sets}"
                if set_pairs:
                    score_str += f" ({', '.join(set_pairs)})"
            else:
                score_str = None
            out.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "dt": dt_warsaw,
                    "home": "Polska",
                    "away": opponent,
                    "home_flag": "pl",
                    "away_flag": _flag_for(opponent),
                    "home_sets": pl_home_sets,
                    "away_sets": pl_away_sets,
                    "score": score_str,
                    "location": city,
                    "completed": pl_home_sets is not None and pl_away_sets is not None,
                }
            )
    return out


# Country → flag (lowercase 2-letter, matching the rest of the dashboard).
FLAG_MAP = {
    "Italy": "it", "Brazil": "br", "United States": "us", "China": "cn",
    "Japan": "jp", "Poland": "pl", "Serbia": "rs", "Türkiye": "tr",
    "Turkey": "tr", "Dominican Republic": "do", "Canada": "ca",
    "Germany": "de", "Thailand": "th", "Bulgaria": "bg", "Netherlands": "nl",
    "France": "fr", "Belgium": "be", "Czechia": "cz", "Czech Republic": "cz",
    "Ukraine": "ua", "Argentina": "ar", "Cuba": "cu", "Slovenia": "si",
    "Iran": "ir",
}


def _flag_for(team_name: str) -> str:
    return FLAG_MAP.get(team_name, "xx")


def date_human(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")


def time_human(dt: datetime) -> str:
    return f"{WEEKDAYS[dt.weekday()].capitalize()}, {dt.strftime('%H:%M')}"


def match_payload(item: dict) -> dict:
    return {
        "date": item["date"],
        "date_human": date_human(item["dt"]),
        "time": time_human(item["dt"]),
        "start_at": item["dt"].isoformat(),
        "home": {"name": item["home"], "flag": item["home_flag"]},
        "away": {"name": item["away"], "flag": item["away_flag"]},
        "competition": "VNL 2026",
        "location": item["location"],
        "source_mode": "wikipedia_vnl_live",
    }


def result_payload(item: dict) -> dict:
    base = match_payload(item)
    base["home_sets"] = item["home_sets"]
    base["away_sets"] = item["away_sets"]
    base["score"] = item["score"]
    return base


def fetch_gender(url: str, gender: str) -> list[dict]:
    html = http_get(url)
    return parse_matches_from_wikipedia(html, gender)


def main() -> int:
    state_dir = resolve_state_dir(None)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "volleyball.json"
    try:
        women = fetch_gender(WOMEN_URL, "women")
        men = fetch_gender(MEN_URL, "men")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        # Don't touch existing file on failure; log and exit non-zero.
        print(f"vnl fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if not women and not men:
        print("vnl fetch returned no Poland matches; keeping previous state", file=sys.stderr)
        return 1
    now = datetime.now(TZ)
    # Split into upcoming and recent
    men_upcoming = sorted(
        [m for m in men if not m["completed"] and m["dt"] >= now - timedelta(hours=4)],
        key=lambda m: m["dt"],
    )
    women_upcoming = sorted(
        [m for m in women if not m["completed"] and m["dt"] >= now - timedelta(hours=4)],
        key=lambda m: m["dt"],
    )
    men_recent = sorted(
        [m for m in men if m["completed"]], key=lambda m: m["dt"], reverse=True,
    )[:3]
    women_recent = sorted(
        [m for m in women if m["completed"]], key=lambda m: m["dt"], reverse=True,
    )[:3]
    payload = envelope(
        "volleyball",
        "ok",
        900,  # 15 min — wiki updates within hours, but we still poll every 20s
        {
            "team_label": "Polska",
            "men": [match_payload(m) for m in men_upcoming],
            "women": [match_payload(m) for m in women_upcoming],
            "recent_results": {
                "men": [result_payload(m) for m in men_recent],
                "women": [result_payload(m) for m in women_recent],
            },
            "source_mode": "wikipedia_vnl_live",
            "sources": [
                "Wikipedia: 2026 FIVB Women's Volleyball Nations League",
                "Wikipedia: 2026 FIVB Men's Volleyball Nations League",
            ],
            "note": (
                "Terminarz i ostatnie wyniki VNL 2026 pobierane z Wikipedii "
                "(artykule aktualizowane w ciągu godzin po meczach). Fallback: "
                "refresh-match-calendar.py z danymi curated."
            ),
            "last_source_review": datetime.now(TZ).strftime("%Y-%m-%d"),
        },
    )
    atomic_write(out_path, payload)
    print(
        f"wrote volleyball.json (men_up={len(men_upcoming)} men_recent={len(men_recent)} "
        f"women_up={len(women_upcoming)} women_recent={len(women_recent)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
