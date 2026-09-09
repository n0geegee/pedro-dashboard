"""Deterministic CEV EuroVolley schedule normalization tests."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eurovolley_schedule import (  # noqa: E402
    build_data,
    parse_cev_final_page,
    static_poland_matches,
    static_schedule_matches,
)


STAMP = "2026-09-06T12:00:00+00:00"


def card(group: int, match: int, code: str, home: str, away: str, date: str, start: str, hs: str = "", ass: str = "") -> str:
    prefix = (
        "ctl00_Content_Left_CompetitionPhase_Details_Calendar_"
        f"RADLIST_Championship_ctrl{group}_RADLIST_Leg_ctrl0_RADLIST_Matches_ctrl{match}"
    )
    def span(suffix: str, value: str) -> str:
        return f'<span id="{prefix}_{suffix}">{value}</span>'
    return "".join([
        span("LB_FMN", code), span("LB_Home", home), span("LB_Guest", away),
        span("LB_Data", date), span("Label1", start), span("Label3", hs),
        span("LB_VintiOspiti", ass),
    ])


class EuroVolleyScheduleTests(unittest.TestCase):
    def test_static_poland_calendar_covers_both_genders_and_real_utc(self) -> None:
        rows = static_poland_matches(STAMP)
        self.assertEqual(len(rows), 10)
        self.assertEqual({row["gender"] for row in rows}, {"K", "M"})
        self.assertEqual(sum(row["gender"] == "K" for row in rows), 5)
        self.assertEqual(sum(row["gender"] == "M" for row in rows), 5)
        self.assertTrue(all(row["start_at"].endswith("+00:00") for row in rows))
        self.assertEqual(rows[0]["warsaw_time"], "18:00")  # Istanbul 19:00 -> PL 18:00
        self.assertEqual(rows[5]["warsaw_time"], "15:00")  # Sofia 16:00 -> PL 15:00

    def test_static_schedule_has_all_six_men_matches_on_10_september(self) -> None:
        rows = [row for row in static_schedule_matches(STAMP) if row["source_date"] == "2026-09-10"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            {(row["home"]["code"], row["away"]["code"]) for row in rows},
            {
                ("POL", "POR"),
                ("ISR", "UKR"),
                ("FIN", "DEN"),
                ("ITA", "SWE"),
                ("FRA", "SUI"),
                ("TUR", "GER"),
            },
        )
        self.assertEqual(
            {row["warsaw_time"] for row in rows},
            {"15:00", "16:00", "18:00", "19:00", "21:05"},
        )

    def test_official_card_parser_normalizes_score_and_phase(self) -> None:
        html = card(9, 0, "WFF-01", "POLAND", "SERBIA", "06/09", "16:00")
        html += card(8, 0, "WSF-01", "POLAND", "ITALY", "04/09", "16:00", "1", "3")
        rows = parse_cev_final_page(html, "K", STAMP)
        by_code = {row["official_code"]: row for row in rows}
        self.assertEqual(set(by_code), {"WFF-01", "WSF-01"})
        final = by_code["WFF-01"]
        self.assertEqual(final["phase"], "Mecz o 3. miejsce")
        self.assertEqual(final["home"]["code"], "POL")
        self.assertEqual(final["status"], "scheduled")
        semi = rows[1]
        self.assertEqual(semi["status"], "finished")
        self.assertEqual(semi["score"], "1:3")

    def test_final_card_can_resolve_date_from_official_match_page(self) -> None:
        html = card(9, 0, "WFF-01", "POLAND", "SERBIA", "", "")
        html += '<div onclick="window.open(\'/Competition-Area/MatchPage.aspx?mID=85105&ID=1573\')"></div>'
        detail = (
            '<span id="Content_Right_MatchInfoBox1_L_MatchDate"><b>06/09/2026</b></span>'
            '<span id="Content_Right_MatchInfoBox1_L_MatchHour"><b>16:00</b></span>'
        )
        seen_urls = []

        def detail_fetch(url: str) -> str:
            seen_urls.append(url)
            return detail

        rows = parse_cev_final_page(html, "K", STAMP, detail_fetch=detail_fetch)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["official_code"], "WFF-01")
        self.assertEqual(rows[0]["source_date"], "2026-09-06")
        self.assertEqual(rows[0]["warsaw_time"], "15:00")
        self.assertEqual(seen_urls, ["https://www-old.cev.eu/Competition-Area/MatchPage.aspx?mID=85105&ID=1573"])

    def test_build_data_exposes_both_competitions_and_warsaw_days(self) -> None:
        html_k = card(9, 0, "WFF-01", "POLAND", "SERBIA", "06/09", "16:00")
        html_m = card(1, 0, "MFB-01", "BULGARIA", "NORTH MACEDONIA", "09/09", "19:00")
        rows = parse_cev_final_page(html_k, "K", STAMP) + parse_cev_final_page(html_m, "M", STAMP)
        data = build_data(rows, STAMP, datetime(2026, 9, 6, 12, tzinfo=timezone.utc))
        self.assertEqual({item["gender"] for item in data["competitions"]}, {"K", "M"})
        self.assertEqual(data["selected_date"], "2026-09-06")
        self.assertTrue(any(row["official_code"] == "WFF-01" for row in data["poland_matches"]))
        self.assertTrue(all(row["timezone"] == "Europe/Warsaw" for row in data["matches"]))
        self.assertEqual(
            [day["date"] for day in data["days"]],
            [
                "2026-08-22", "2026-08-24", "2026-08-25", "2026-08-27", "2026-08-28",
                "2026-09-06", "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-12",
                "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17",
            ],
        )
        sep10 = next(day for day in data["days"] if day["date"] == "2026-09-10")
        self.assertEqual(len(sep10["matches"]), 6)
        self.assertEqual(
            {(row["home"]["code"], row["away"]["code"]) for row in sep10["matches"]},
            {
                ("POL", "POR"),
                ("ISR", "UKR"),
                ("FIN", "DEN"),
                ("ITA", "SWE"),
                ("FRA", "SUI"),
                ("TUR", "GER"),
            },
        )
        self.assertTrue(any(row["id"] == "M-calendar-M-2026-09-10-POL-POR" for row in data["matches"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
