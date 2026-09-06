"""Unit tests for the extracted Pedro Dashboard state helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from app import state_store


class StateStoreUnitTests(unittest.TestCase):
    def test_read_json_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok, payload, error = state_store.read_json(Path(tmp) / "missing.json")
        self.assertFalse(ok)
        self.assertIsNone(payload)
        self.assertEqual(error, "missing:missing.json")

    def test_read_json_malformed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{broken", encoding="utf-8")
            ok, payload, error = state_store.read_json(path)
        self.assertFalse(ok)
        self.assertIsNone(payload)
        self.assertTrue(error.startswith("json_decode_error:"))

    def test_read_json_success_preserves_none_error_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"status": "ok", "value": 7}', encoding="utf-8")
            ok, payload, error = state_store.read_json(path)
        self.assertTrue(ok)
        self.assertEqual(payload, {"status": "ok", "value": 7})
        self.assertIsNone(error)

    def test_read_json_directory_is_io_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "directory"
            path.mkdir()
            ok, payload, error = state_store.read_json(path)
        self.assertFalse(ok)
        self.assertIsNone(payload)
        self.assertTrue(error.startswith("io_error:"))

    def test_is_stale_handles_ttl_and_timestamps(self) -> None:
        now = datetime.now(timezone.utc)
        self.assertFalse(state_store.is_stale(now.isoformat(), 0))
        self.assertFalse(state_store.is_stale(now.isoformat(), None))
        self.assertTrue(state_store.is_stale(None, 10))
        self.assertTrue(state_store.is_stale("not-a-timestamp", 10))
        self.assertTrue(state_store.is_stale((now - timedelta(seconds=30)).isoformat(), 10))
        self.assertFalse(state_store.is_stale((now + timedelta(seconds=30)).isoformat(), 10))

    def test_is_stale_treats_naive_timestamp_as_utc(self) -> None:
        naive_past = (datetime.now(timezone.utc) - timedelta(seconds=30)).replace(tzinfo=None)
        self.assertTrue(state_store.is_stale(naive_past.isoformat(), 10))

    def test_empty_envelope_shape_and_privacy(self) -> None:
        envelope = state_store.empty_envelope(
            "calendar", status="error", error="broken", privacy_mode="private"
        )
        self.assertEqual(
            envelope,
            {
                "status": "error",
                "updated_at": None,
                "ttl_seconds": None,
                "privacy_mode": "private",
                "data": {},
                "error": "broken",
                "_widget": "calendar",
            },
        )

    def test_server_uses_extracted_helpers(self) -> None:
        from app import server

        self.assertIs(server._read_json, state_store.read_json)
        self.assertIs(server._is_stale, state_store.is_stale)
        self.assertIs(server._empty_envelope, state_store.empty_envelope)


if __name__ == "__main__":
    unittest.main(verbosity=2)
