"""Birdwatch LL card probe + API contract tests.

Two layers:

* :class:`LlTbdApiContractTests` hits the live dashboard server
  ``/api/state`` and asserts that the LL card payload has
  ``data.kind == "birdwatch"`` and the audio envelope is structurally valid.
  Skipped automatically when the server is unreachable so this file is safe
  to run in CI without a kiosk.
* :class:`RefreshBirdwatchProbeTests` exercises
  ``scripts/refresh-birdwatch-status.py`` against a controlled fixture
  (no live BirdNET-Go required). It writes to a temporary state directory
  via ``--out`` so it never touches the real ``app/state/ll_tbd.json``.

Run with stdlib unittest only — no pytest, no third-party deps.

    python3 -m unittest discover -s tests -p 'test_*.py' -v
"""
from __future__ import annotations

import json
import importlib.util
import os
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
DEFAULT_BASE = os.environ.get("PEDRO_TEST_URL", "http://127.0.0.1:17888")
TIMEOUT = float(os.environ.get("PEDRO_TEST_TIMEOUT", "5"))


def _load_probe_module():
    spec = importlib.util.spec_from_file_location(
        "pedro_birdwatch_probe", SCRIPTS_DIR / "refresh-birdwatch-status.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Birdwatch probe module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _urlopen_json(path: str):
    with urlopen(f"{DEFAULT_BASE}{path}", timeout=TIMEOUT) as r:
        return json.load(r), r.status


def _is_dashboard_up() -> bool:
    try:
        _urlopen_json("/api/health")
        return True
    except (URLError, OSError, ValueError):
        return False


def _polish_common_hint() -> dict:
    """A copy of the PL hint mapping from the probe. We only assert that
    scientific -> polish mapping works for a known species; we don't import
    from the probe module because it has side-effects on import (logging,
    sys.path)."""
    return {
        "Turdus merula": "Kos",
        "Erithacus rubecula": "Rudzik",
        "Parus major": "Bogatka",
        "Pica pica": "Sroka",
    }


# ---------------------------------------------------------------------------
# API contract tests (live)
# ---------------------------------------------------------------------------


@unittest.skipUnless(_is_dashboard_up(), "Dashboard server not reachable; skipping live API tests")
class LlTbdApiContractTests(unittest.TestCase):
    """``/api/state.widgets.ll_tbd.data.kind`` must equal ``"birdwatch"``."""

    def test_ll_tbd_kind_is_birdwatch(self) -> None:
        body, _ = _urlopen_json("/api/state")
        ll = body["widgets"].get("ll_tbd")
        self.assertIsNotNone(ll, "ll_tbd missing from /api/state.widgets")
        self.assertIn("data", ll)
        self.assertEqual(
            ll["data"].get("kind"),
            "birdwatch",
            f"unexpected ll_tbd kind: {ll['data'].get('kind')!r}",
        )

    def test_ll_tbd_envelope_shape(self) -> None:
        body, _ = _urlopen_json("/api/state")
        ll = body["widgets"]["ll_tbd"]
        # Always-present fields (D-002 contract on envelope shape).
        for key in ("status", "updated_at", "ttl_seconds", "privacy_mode", "data"):
            self.assertIn(key, ll, f"ll_tbd missing top-level key: {key}")
        self.assertIn(
            ll["status"], ("ok", "stale", "error", "empty", "disabled"),
            f"unexpected ll_tbd status: {ll['status']!r}",
        )

    def test_ll_tbd_data_birdwatch_shape(self) -> None:
        body, _ = _urlopen_json("/api/state")
        d = body["widgets"]["ll_tbd"]["data"]
        # Birdwatch sub-payload: every key the UI depends on must be present.
        for key in (
            "kind",
            "title",
            "subtitle",
            "station",
            "audio",
            "detections",
            "empty_message",
        ):
            self.assertIn(key, d, f"ll_tbd.data missing key: {key}")
        self.assertEqual(d["kind"], "birdwatch")
        self.assertEqual(d["title"], "PTAKI ZA OKNEM")
        # Audio envelope must not leak secrets (no env values, no paths).
        audio = d["audio"]
        self.assertIn(audio.get("status"), ("ok", "missing", "unknown"))
        for forbidden in ("api_key", "token", "password", "PASSWORD", "API_KEY"):
            self.assertNotIn(forbidden, audio, "audio leaked a forbidden field")
        # Detections list, when present, must be an array.
        self.assertIsInstance(d["detections"], list)


# ---------------------------------------------------------------------------
# Probe unit tests (offline, with a fixture)
# ---------------------------------------------------------------------------


def _build_recent_fixture(path: Path) -> None:
    """Write a fixture with timestamps relative to *now* (deterministic-ish)."""
    now = datetime.now(timezone.utc)
    iso = lambda m: (now - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
    det = [
        {"heard_at": iso(1),  "scientific": "Turdus merula",      "common_en": "Common Blackbird", "confidence": 0.92, "station": "taras", "source": "birdnet"},
        {"heard_at": iso(5),  "scientific": "Erithacus rubecula", "common_en": "European Robin",   "confidence": 0.84, "station": "taras", "source": "birdnet"},
        {"heard_at": iso(10), "scientific": "Parus major",        "common_en": "Great Tit",        "confidence": 0.78, "station": "taras", "source": "birdnet"},
        {"heard_at": iso(15), "scientific": "Pica pica",          "common_en": "Eurasian Magpie",  "confidence": 0.55, "station": "taras", "source": "birdnet"},
        {"heard_at": iso(25), "scientific": "Sturnus vulgaris",   "common_en": "Common Starling",  "confidence": 0.81, "station": "taras", "source": "birdnet"},
    ]
    with path.open("w", encoding="utf-8") as f:
        json.dump({"detections": det}, f, ensure_ascii=False, indent=2)


class RefreshBirdwatchProbeTests(unittest.TestCase):
    """Exercise ``scripts/refresh-birdwatch-status.py`` against a fixture.

    These tests NEVER call the live BirdNET/HTTP path. They use
    ``BIRDWATCH_SOURCE_JSON`` so the probe treats the file as an authoritative
    detection source. Output is written to a ``tempfile.TemporaryDirectory``
    via ``--out`` so the real ``app/state/ll_tbd.json`` is untouched.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.workdir = tempfile.TemporaryDirectory(prefix="pedro-birdwatch-test-")
        cls.tmp_root = Path(cls.workdir.name)
        cls.probe = SCRIPTS_DIR / "refresh-birdwatch-status.py"
        if not cls.probe.exists():
            raise unittest.SkipTest(f"missing probe: {cls.probe}")
        cls.probe_module = _load_probe_module()
        cls.fixtures = cls.tmp_root / "fixtures"
        cls.fixtures.mkdir(parents=True, exist_ok=True)
        cls.out_dir = cls.tmp_root / "state"
        cls.out_dir.mkdir(parents=True, exist_ok=True)
        cls.fixture = cls.fixtures / "birdwatch_detections.json"
        _build_recent_fixture(cls.fixture)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.workdir.cleanup()

    def _run_probe(self, env_overrides: dict | None = None) -> dict:
        env = os.environ.copy()
        env["BIRDWATCH_SOURCE_JSON"] = str(self.fixture)
        env["BIRDWATCH_MIN_CONFIDENCE"] = "0.70"
        env["BIRDWATCH_WINDOW_MINUTES"] = "20"
        env["BIRDWATCH_MAX_ROWS"] = "7"
        if env_overrides:
            env.update(env_overrides)
        # Python from env if caller set one; else default to system python.
        result = subprocess.run(
            [sys.executable, str(self.probe), "--out", str(self.out_dir), "--ttl", "90"],
            capture_output=True, text=True, env=env, timeout=20, check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            f"probe failed: stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        with (self.out_dir / "ll_tbd.json").open(encoding="utf-8") as f:
            return json.load(f)

    def test_envelope_has_birdwatch_kind(self) -> None:
        payload = self._run_probe()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["kind"], "birdwatch")
        self.assertEqual(payload["data"]["title"], "PTAKI ZA OKNEM")

    def test_detections_sorted_desc_by_heard_at(self) -> None:
        payload = self._run_probe()
        det = payload["data"]["detections"]
        timestamps = [d["heard_at"] for d in det]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_low_confidence_filtered_out(self) -> None:
        payload = self._run_probe()
        for d in payload["data"]["detections"]:
            self.assertGreaterEqual(
                d["confidence"], 0.70,
                f"detection under threshold leaked: {d}",
            )

    def test_outside_window_filtered_out(self) -> None:
        payload = self._run_probe()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=20)
        for d in payload["data"]["detections"]:
            ts = datetime.fromisoformat(d["heard_at"].replace("Z", "+00:00"))
            self.assertGreaterEqual(
                ts, cutoff,
                f"detection outside 20-min window leaked: {d}",
            )

    def test_polish_common_name_mapped(self) -> None:
        """For every scientific name in the output, the PL hint must match.

        The probe filters by confidence and window, so we only check the
        rows that survived — the assertion is about the *mapping*, not
        about specific detections being present.
        """
        payload = self._run_probe()
        spec_to_pl = {d["scientific"]: (d.get("species_pl") or "") for d in payload["data"]["detections"]}
        # If the hint ever updates or the confidence threshold changes,
        # this test should still pass for any output row whose scientific
        # is in the hint table.
        hints = _polish_common_hint()
        common = set(spec_to_pl) & set(hints)
        if not common:
            self.skipTest("no overlapping species survived filtering in this run")
        for sci in common:
            self.assertEqual(
                spec_to_pl[sci], hints[sci],
                f"scientific {sci} mapped to {spec_to_pl[sci]!r}, expected {hints[sci]!r}",
            )

    def test_max_rows_capped(self) -> None:
        # With 4 in-window detections (5-1=4 minus the out-of-window one),
        # asking for 2 must yield exactly 2.
        payload = self._run_probe({"BIRDWATCH_MAX_ROWS": "2"})
        self.assertEqual(len(payload["data"]["detections"]), 2)

    def test_audio_envelope_has_required_keys(self) -> None:
        payload = self._run_probe()
        audio = payload["data"]["audio"]
        for key in ("status", "device", "sample_rate", "last_audio_at", "message"):
            self.assertIn(key, audio, f"audio missing key: {key}")
        self.assertIn(audio["status"], ("ok", "missing", "unknown"))

    def test_fresh_flag_set_for_recent(self) -> None:
        payload = self._run_probe()
        det = payload["data"]["detections"]
        if det:
            most_recent = det[0]
            self.assertTrue(
                most_recent["fresh"],
                f"the freshest detection should be flagged fresh: {most_recent}",
            )

    def test_no_secrets_in_payload(self) -> None:
        payload = self._run_probe()
        # Quick privacy sweep: we never want raw env values / PII / paths.
        text = json.dumps(payload, ensure_ascii=False).lower()
        for forbidden in (
            "password", "api_key=", "token=", "/home/", "/root/",
            "ssh ", "passphrase", "cookie=",
        ):
            self.assertNotIn(forbidden, text, f"forbidden token leaked: {forbidden}")

    def test_tolerant_when_source_missing(self) -> None:
        """Probe must still produce a valid envelope when no source is reachable."""
        env_overrides = {
            "BIRDWATCH_SOURCE_JSON": "/nonexistent/path/fixture.json",
            "BIRDNET_GO_DB": "/nonexistent/birdnet.db",
            "BIRDNET_GO_HTTP": "",
        }
        payload = self._run_probe(env_overrides)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["kind"], "birdwatch")
        self.assertEqual(payload["data"]["source"], "none")
        self.assertEqual(payload["data"]["detections"], [])

    def test_sqlite_note_adapter_reads_birdnet_rows(self) -> None:
        """The production SQLite adapter must read a BirdNET-Go note row."""
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory(prefix="pedro-birdwatch-db-") as td:
            db = Path(td) / "birdnet.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE note ("
                "Date TEXT, Time TEXT, ScientificName TEXT, CommonName TEXT, "
                "Confidence REAL, Station TEXT)"
            )
            conn.execute(
                "INSERT INTO note VALUES (?, ?, ?, ?, ?, ?)",
                (
                    now.isoformat().replace("+00:00", "Z"),
                    "",
                    "Turdus merula",
                    "Common Blackbird",
                    0.91,
                    "taras",
                ),
            )
            conn.commit()
            conn.close()

            rows = self.probe_module._read_birdnet_db(
                db, now - timedelta(minutes=20)
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["scientific"], "Turdus merula")
        self.assertEqual(rows[0]["common_en"], "Common Blackbird")
        self.assertAlmostEqual(rows[0]["confidence"], 0.91)

    def test_sqlite_date_and_time_columns_are_combined(self) -> None:
        ts = self.probe_module._combine_birdnet_timestamp(
            {"Date": "2026-01-15", "Time": "14:30:00"},
            {"date", "time"},
        )
        self.assertEqual(
            ts,
            datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc),
        )

    def test_warsaw_label_observes_winter_and_summer_dst(self) -> None:
        self.assertEqual(
            self.probe_module._format_warsaw_label("2026-01-15T12:00:00Z"),
            "13:00",
        )
        self.assertEqual(
            self.probe_module._format_warsaw_label("2026-07-15T12:00:00Z"),
            "14:00",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
