"""Unit tests for the local Pedro slideshow control state."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.display_control import (
    ControlStateError,
    apply_action,
    default_state,
    read_control_state,
    transition,
    validate_control_state,
    write_control_state,
)


class DisplayControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "display-control.json"
        self.now = datetime(2026, 9, 10, 18, 30, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_missing_file_is_fail_safe_off(self) -> None:
        result = read_control_state(self.path)
        self.assertFalse(result.valid)
        self.assertEqual(result.error, "missing")
        self.assertFalse(result.state["enabled"])
        self.assertEqual(result.state["photo_seconds"], 2)

    def test_on_off_and_restart_are_idempotent(self) -> None:
        state, changed, _ = apply_action("on", self.path, now=self.now)
        self.assertTrue(changed)
        self.assertTrue(state["enabled"])
        cycle_started = state["cycle_started_at"]
        generation = state["generation"]

        again, changed, _ = apply_action(
            "on", self.path, now=datetime(2026, 9, 10, 18, 31, tzinfo=timezone.utc)
        )
        self.assertFalse(changed)
        self.assertEqual(again["cycle_started_at"], cycle_started)
        self.assertEqual(again["generation"], generation)

        off, changed, _ = apply_action("off", self.path, now=self.now)
        self.assertTrue(changed)
        self.assertFalse(off["enabled"])
        off_generation = off["generation"]
        off_again, changed, _ = apply_action("off", self.path, now=self.now)
        self.assertFalse(changed)
        self.assertEqual(off_again["generation"], off_generation)

        restarted, changed, _ = apply_action("restart-cycle", self.path, now=self.now + timedelta(seconds=1))
        self.assertTrue(changed)
        self.assertTrue(restarted["enabled"])
        self.assertNotEqual(restarted["cycle_started_at"], cycle_started)
        self.assertGreater(restarted["generation"], off_generation)

    def test_write_is_atomic_and_private(self) -> None:
        state, _ = transition(default_state(), "on", now=self.now)
        write_control_state(state, self.path)
        mode = stat.S_IMODE(self.path.stat().st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(self.path.stat().st_uid, os.getuid())
        result = read_control_state(self.path)
        self.assertTrue(result.valid)
        self.assertEqual(result.state, state)
        self.assertFalse(list(Path(self.tempdir.name).glob("*.tmp")))

    def test_invalid_json_unknown_fields_and_wrong_mode_fail_safe(self) -> None:
        self.path.write_text("not json", encoding="utf-8")
        os.chmod(self.path, 0o600)
        result = read_control_state(self.path)
        self.assertFalse(result.valid)
        self.assertFalse(result.state["enabled"])

        state, _ = transition(default_state(), "on", now=self.now)
        state["unexpected"] = True
        with self.assertRaisesRegex(ControlStateError, "unknown_fields"):
            validate_control_state(state)

        valid_state, _ = transition(default_state(), "on", now=self.now)
        write_control_state(valid_state, self.path)
        os.chmod(self.path, 0o644)
        result = read_control_state(self.path)
        self.assertFalse(result.valid)
        self.assertEqual(result.error, "control_file_wrong_mode")
        self.assertFalse(result.state["enabled"])

    def test_symlink_is_rejected(self) -> None:
        target = Path(self.tempdir.name) / "target.json"
        target.write_text(json.dumps({}), encoding="utf-8")
        self.path.symlink_to(target)
        result = read_control_state(self.path)
        self.assertFalse(result.valid)
        self.assertEqual(result.error, "control_file_is_symlink")

    def test_transition_rejects_unknown_action(self) -> None:
        with self.assertRaisesRegex(ControlStateError, "unknown_action"):
            transition(default_state(), "toggle")

    def test_cli_switch_controls_state_and_rotator(self) -> None:
        calls = Path(self.tempdir.name) / "rotator.calls"
        stub = Path(self.tempdir.name) / "rotator-stub"
        stub.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$PEDRO_TEST_CALLS\"\nexit 0\n",
            encoding="utf-8",
        )
        stub.chmod(0o700)
        env = os.environ.copy()
        env.update(
            {
                "PEDRO_DISPLAY_CONTROL_FILE": str(self.path),
                "PEDRO_PHOTOS_ROTATOR_SCRIPT": str(stub),
                "PEDRO_TEST_CALLS": str(calls),
            }
        )
        wrapper = Path(__file__).resolve().parents[1] / "scripts" / "slideshow"

        def run(*args: str) -> dict[str, object]:
            completed = subprocess.run(
                [str(wrapper), *args],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(completed.stdout)

        run("on")
        first = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(first["enabled"])
        run("on")
        second = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(second["cycle_started_at"], first["cycle_started_at"])
        run("off")
        final = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertFalse(final["enabled"])
        calls_text = calls.read_text(encoding="utf-8")
        self.assertIn("--start --interval 2", calls_text)
        self.assertIn("--stop", calls_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
