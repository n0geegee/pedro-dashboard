"""Regression contracts for the slideshow single-owner pipeline.

These tests deliberately inspect the small operator/runtime contracts rather
than trying to launch the real kiosk from CI. The live verification still
exercises the scripts and native display after the patch.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STATIC = ROOT / "app" / "static"


class SlideshowRegressionTests(unittest.TestCase):
    def test_media_state_lock_serializes_two_processes(self) -> None:
        """The shared media lock must serialize real competing writers."""
        code = """
import os
import time
from pathlib import Path
from _probe_common import media_state_lock

state_dir = Path(os.environ["STATE_DIR"])
marker = Path(os.environ["MARKER"])
label = os.environ["LABEL"]
with media_state_lock(state_dir):
    with marker.open("a", encoding="utf-8") as handle:
        handle.write(f"enter:{label}\\n")
    time.sleep(0.15)
    with marker.open("a", encoding="utf-8") as handle:
        handle.write(f"exit:{label}\\n")
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = os.environ.copy()
            env.update(
                {
                    "PYTHONPATH": str(SCRIPTS),
                    "PEDRO_PHOTOS_LOCK_FILE": str(root / "media.lock"),
                    "STATE_DIR": str(root / "state"),
                    "MARKER": str(root / "events.log"),
                }
            )
            first_env = {**env, "LABEL": "one"}
            first = subprocess.Popen([sys.executable, "-c", code], env=first_env)
            marker = root / "events.log"
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if marker.exists() and "enter:one\n" in marker.read_text(encoding="utf-8"):
                    break
                time.sleep(0.01)
            else:
                first.kill()
                self.fail("first writer never acquired the media lock")

            second_env = {**env, "LABEL": "two"}
            second = subprocess.Popen([sys.executable, "-c", code], env=second_env)
            self.assertEqual(first.wait(timeout=3), 0)
            self.assertEqual(second.wait(timeout=3), 0)
            self.assertEqual(
                marker.read_text(encoding="utf-8").splitlines(),
                ["enter:one", "exit:one", "enter:two", "exit:two"],
            )

    def test_probe_serializes_read_modify_write(self) -> None:
        common = (SCRIPTS / "_probe_common.py").read_text(encoding="utf-8")
        photos = (SCRIPTS / "refresh-photos-slideshow.py").read_text(encoding="utf-8")
        polsat = (SCRIPTS / "refresh-polsat-status.py").read_text(encoding="utf-8")
        self.assertIn("def media_state_lock", common)
        self.assertIn("media_state_lock", photos)
        self.assertIn("media_state_lock", polsat)
        self.assertIn("/var/lock/pedro-photos.lock", common)

    def test_rotator_waits_after_probe_instead_of_zero_sleep_catch_up(self) -> None:
        source = (SCRIPTS / "photos-rotator.sh").read_text(encoding="utf-8")
        self.assertIn('sleep "$INTERVAL"', source)
        self.assertNotIn("remaining=$(awk", source)
        self.assertNotIn('sleep "$remaining"', source)

    def test_hot_rotation_does_not_block_on_manifest_refresh(self) -> None:
        rotator = (SCRIPTS / "photos-rotator.sh").read_text(encoding="utf-8")
        refresher = (SCRIPTS / "refresh-all-state.sh").read_text(encoding="utf-8")
        probe = (SCRIPTS / "refresh-photos-slideshow.py").read_text(encoding="utf-8")
        self.assertIn("--no-manifest-refresh", rotator)
        self.assertIn("--manifest-only", refresher)
        self.assertIn("manifest_only", probe)
        self.assertIn("no_manifest_refresh", probe)

    def test_queue_rebuild_continues_after_current_public_url(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("refresh_photos", SCRIPTS / "refresh-photos-slideshow.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest = {
            "images": [
                {"public_url": "/static/cache/photos/a.webp"},
                {"public_url": "/static/cache/photos/b.webp"},
                {"public_url": "/static/cache/photos/c.webp"},
            ]
        }
        current, image = module.pick_image(
            manifest,
            slide_seconds=2,
            last_index=0,
            last_public_url="/static/cache/photos/b.webp",
        )
        self.assertEqual(current, 3)
        self.assertEqual(image["public_url"], "/static/cache/photos/c.webp")

    def test_manifest_refresh_preserves_existing_queue_order(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("refresh_photos_order", SCRIPTS / "refresh-photos-slideshow.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        previous = {
            "images": [
                {"public_url": "/static/cache/photos/b.webp"},
                {"public_url": "/static/cache/photos/a.webp"},
            ]
        }
        fresh = [
            {"public_url": "/static/cache/photos/a.webp"},
            {"public_url": "/static/cache/photos/c.webp"},
            {"public_url": "/static/cache/photos/b.webp"},
        ]
        ordered = module.preserve_manifest_order(fresh, previous)
        self.assertEqual(
            [item["public_url"] for item in ordered],
            [
                "/static/cache/photos/b.webp",
                "/static/cache/photos/a.webp",
                "/static/cache/photos/c.webp",
            ],
        )

    def test_orientation_changes_only_incoming_layer_and_policy_is_shared(self) -> None:
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        css = (STATIC / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn('var wasActive = layers[i].classList.contains("is-active");', js)
        self.assertNotIn("background-size: auto 106%", css)
        self.assertNotIn("background-size: auto 104%", css)
        self.assertNotIn("transform: scale(1.002)", css)
        self.assertGreaterEqual(css.count("background-size: contain;"), 2)

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
        self.assertIn("--disable-background-networking", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
