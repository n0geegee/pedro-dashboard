"""Pedro Dashboard contract smoke tests (stdlib unittest, no pytest).

These tests hit a running dashboard server on 127.0.0.1:17888 by default
(PEDRO_TEST_URL env override allowed). They validate the contract that
the frontend depends on — anything that breaks these tests likely broke
the kiosk.

Run:
    python3 -m unittest discover -s tests -p 'test_*.py' -v

Exit code 0 == all green; non-zero == at least one contract violated.
"""
from __future__ import annotations

import json
import os
import unittest
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_BASE = os.environ.get("PEDRO_TEST_URL", "http://127.0.0.1:17888")
TIMEOUT = float(os.environ.get("PEDRO_TEST_TIMEOUT", "5"))


def _get_json(path: str):
    with urlopen(f"{DEFAULT_BASE}{path}", timeout=TIMEOUT) as r:
        return json.load(r), r.status


class HealthContractTests(unittest.TestCase):
    """GET /api/health must report port=17888 and a JSON body."""

    def test_health_returns_200(self) -> None:
        _, status = _get_json("/api/health")
        self.assertEqual(status, 200)

    def test_health_has_required_keys(self) -> None:
        body, _ = _get_json("/api/health")
        for key in ("status", "service", "host", "port", "privacy_mode"):
            self.assertIn(key, body, f"missing key: {key}")

    def test_health_status_is_ok(self) -> None:
        body, _ = _get_json("/api/health")
        self.assertEqual(body["status"], "ok")

    def test_health_service_is_pedro(self) -> None:
        body, _ = _get_json("/api/health")
        self.assertEqual(body["service"], "pedro_dashboard")

    def test_health_port_is_17888(self) -> None:
        body, _ = _get_json("/api/health")
        self.assertEqual(body["port"], 17888)

    def test_health_host_is_loopback(self) -> None:
        body, _ = _get_json("/api/health")
        self.assertIn(body["host"], ("127.0.0.1", "localhost"))

    def test_health_version_is_semver_like(self) -> None:
        body, _ = _get_json("/api/health")
        v = body.get("version", "")
        # Either a real version like 1.4.11 or 0.0.0 fallback; never empty.
        self.assertTrue(v, "version is empty")
        parts = v.split(".")
        self.assertGreaterEqual(len(parts), 2, f"version not dotted: {v!r}")


class StateContractTests(unittest.TestCase):
    """GET /api/state must expose top-level `widgets` envelope."""

    def test_state_returns_200(self) -> None:
        _, status = _get_json("/api/state")
        self.assertEqual(status, 200)

    def test_state_has_top_level_widgets(self) -> None:
        body, _ = _get_json("/api/state")
        self.assertIn("widgets", body, f"top-level keys: {sorted(body)}")

    def test_state_widgets_is_dict(self) -> None:
        body, _ = _get_json("/api/state")
        self.assertIsInstance(body["widgets"], dict)

    def test_state_has_required_top_level_keys(self) -> None:
        body, _ = _get_json("/api/state")
        for key in ("status", "updated_at", "privacy_mode", "server", "widgets"):
            self.assertIn(key, body, f"missing key: {key}")

    def test_state_server_block_reports_17888(self) -> None:
        body, _ = _get_json("/api/state")
        self.assertEqual(body["server"]["port"], 17888)

    def test_state_widgets_include_voice_console(self) -> None:
        body, _ = _get_json("/api/state")
        self.assertIn("voice_console", body["widgets"])

    def test_state_widget_envelopes_have_status(self) -> None:
        body, _ = _get_json("/api/state")
        # Spot-check that at least the widgets we depend on are valid envelopes.
        for widget in ("weather", "calendar", "system", "voice_console"):
            with self.subTest(widget=widget):
                env = body["widgets"].get(widget)
                if env is None:
                    continue  # not exposed at audit time, skip silently
                self.assertIn("status", env)
                self.assertIn(
                    env["status"],
                    ("ok", "stale", "error", "empty", "disabled"),
                )


class VoiceConsoleContractTests(unittest.TestCase):
    """GET /api/voice_console must keep voice/utterance/activity/result at
    the top level (NOT collapsed inside a `data` envelope)."""

    def test_voice_console_returns_200(self) -> None:
        _, status = _get_json("/api/voice_console")
        self.assertEqual(status, 200)

    def test_voice_console_top_level_keys(self) -> None:
        body, _ = _get_json("/api/voice_console")
        for key in ("voice", "utterance", "activity", "result", "error"):
            self.assertIn(key, body, f"missing top-level key: {key}")

    def test_voice_console_privacy_mode_present(self) -> None:
        body, _ = _get_json("/api/voice_console")
        self.assertIn(body.get("privacy_mode"), ("private", "guest"))

    def test_voice_console_widget_marker(self) -> None:
        body, _ = _get_json("/api/voice_console")
        self.assertEqual(body.get("_widget"), "voice_console")


if __name__ == "__main__":
    try:
        _get_json("/api/health")
    except URLError as exc:
        raise SystemExit(
            f"dashboard server not reachable at {DEFAULT_BASE}: {exc}"
        )
    unittest.main(verbosity=2)
