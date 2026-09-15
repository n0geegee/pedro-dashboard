"""Match-day skin detection across competitions and both genders."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import server  # noqa: E402


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
MATCH_START = "2026-09-06T13:00:00+00:00"  # 15:00 Europe/Warsaw


class MatchdayDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_state_dir = server.STATE_DIR
        self.old_state_files = server.STATE_FILES
        server.STATE_DIR = Path(self.tmp.name)

    def tearDown(self) -> None:
        server.STATE_DIR = self.old_state_dir
        server.STATE_FILES = self.old_state_files
        self.tmp.cleanup()

    def write_widget(self, name: str, data) -> None:
        (Path(self.tmp.name) / f"{name}.json").write_text(
            json.dumps({"status": "ok", "data": data}), encoding="utf-8"
        )
        server.STATE_FILES = {name: f"{name}.json"}

    def test_womens_eurovolley_bronze_match_activates_skin(self) -> None:
        self.write_widget(
            "eurovolley",
            {
                "days": [
                    {
                        "date": "2026-09-06",
                        "matches": [
                            {
                                "competition": "CEV Trendyol EuroVolley 2026 Women",
                                "gender": "K",
                                "phase": "Mecz o 3. miejsce",
                                "status": "finished",
                                "home": {"code": "POL", "name": "Polska", "flag": "pl"},
                                "away": {"code": "SRB", "name": "Serbia", "flag": "srb"},
                                "start_at": MATCH_START,
                            }
                        ],
                    }
                ]
            },
        )
        self.assertTrue(server._poland_match_today(NOW))

    def test_mens_and_womens_friendlies_use_same_generic_trigger(self) -> None:
        cases = [
            ("men", "M", {"name": "Polska", "code": "POL"}, {"name": "Niemcy", "code": "GER"}),
            ("women", "K", {"name": "Francja", "code": "FRA"}, {"name": "Polska", "code": "POL"}),
        ]
        for name, gender, home, away in cases:
            with self.subTest(gender=gender):
                self.write_widget(
                    name,
                    {
                        "competition": "Mecz towarzyski",
                        "gender": gender,
                        "matches": [
                            {
                                "competition": "Mecz towarzyski",
                                "gender": gender,
                                "home": home,
                                "away": away,
                                "start_at": MATCH_START,
                            }
                        ],
                    },
                )
                self.assertTrue(server._poland_match_today(NOW))

    def test_past_malformed_and_other_day_matches_do_not_activate_skin(self) -> None:
        self.write_widget(
            "mixed",
            {
                "matches": [
                    {
                        "home": {"name": "Polska"},
                        "away": {"name": "Czechia"},
                        "start_at": "2026-09-05T13:00:00+00:00",
                    },
                    {
                        "home": {"name": "Polska"},
                        "away": {"name": "Czechia"},
                        "start_at": "not-a-timestamp",
                    },
                    {
                        "home": {"name": "Polska"},
                        "away": {"name": "Czechia"},
                        "start_at": "2026-09-07T13:00:00+00:00",
                    },
                ]
            },
        )
        self.assertFalse(server._poland_match_today(NOW))


if __name__ == "__main__":
    unittest.main(verbosity=2)