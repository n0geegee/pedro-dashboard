"""Regression contracts for the slideshow single-owner pipeline.

These tests deliberately inspect the small operator/runtime contracts rather
than trying to launch the real kiosk from CI. The live verification still
exercises the scripts and native display after the patch.
"""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STATIC = ROOT / "app" / "static"


class SlideshowRegressionTests(unittest.TestCase):
    def test_probe_serializes_read_modify_write(self) -> None:
        source = (SCRIPTS / "refresh-photos-slideshow.py").read_text(encoding="utf-8")
        self.assertIn("import fcntl", source)
        self.assertIn("/var/lock/pedro-photos.lock", source)
        self.assertIn("fcntl.flock", source)

    def test_rotator_has_a_single_loop_owner(self) -> None:
        source = (SCRIPTS / "photos-rotator.sh").read_text(encoding="utf-8")
        self.assertIn("/var/lock/pedro-photos-rotator.lock", source)
        self.assertIn("flock", source)

    def test_fallback_probe_checks_actual_rotator_owner(self) -> None:
        source = (SCRIPTS / "refresh-all-state.sh").read_text(encoding="utf-8")
        self.assertIn('pedro_pid_matches_all "$photos_pid" "photos-rotator.sh" "--loop"', source)

    def test_frontend_never_replays_stale_media_snapshot(self) -> None:
        source = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("activeMediaWidget || w.media", source)
        self.assertIn("data-pending-url", source)
        self.assertIn("renderState", source)

    def test_kiosk_suppresses_native_chrome_bubbles(self) -> None:
        source = (SCRIPTS / "start-kiosk.sh").read_text(encoding="utf-8")
        self.assertIn("--noerrdialogs", source)
        self.assertIn("--disable-session-crashed-bubble", source)
        self.assertIn("--disable-component-update", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
