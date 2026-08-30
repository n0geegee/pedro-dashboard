"""Tolerant JSON state I/O + stale detection for Pedro Dashboard.

Extracted from ``app/server.py`` (Phase 3 / Commit D). Pure refactor:
no behavioral change. Every public function here was previously a
private helper in ``server.py`` and is now also re-exported from there
to keep any future external importer working.

Public surface (helpers only — ``load_widget`` and
``load_aggregated_state`` stay in ``server.py`` for now because they
are coupled to the voice-console contract and to the rollup fields
``server`` + ``poland_match_today`` that the UI consumes):

* :func:`read_json`        - tolerant JSON read, returns (ok, payload, error)
* :func:`is_stale`         - TTL check with malformed-timestamp fallback
* :func:`empty_envelope`   - canonical empty envelope for a widget

All functions accept paths as :class:`pathlib.Path` so the caller can
decide where state files live. ``server.py`` re-exports these helpers
under their legacy underscore-prefixed names to keep any future
external importer working.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def read_json(path: Path) -> Tuple[bool, Any, Optional[str]]:
    """Tolerant JSON read.

    Returns a 3-tuple ``(ok, payload, error_message)``:

    * ``ok`` is ``False`` when the file is missing, malformed, or unreadable.
    * ``payload`` is the decoded JSON on success, ``None`` on failure.
    * ``error_message`` is a short, log-friendly string on failure, or
      ``None`` on success (matching the historical ``_read_json`` contract
      in ``server.py``; callers branch on ``ok``).

    Never raises. Callers are expected to branch on ``ok`` and treat a
    ``False`` value as "use the empty envelope" rather than as a fatal error.
    """
    if not path.exists():
        return False, None, f"missing:{path.name}"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        return False, None, f"json_decode_error:{exc.msg}@line{exc.lineno}"
    except OSError as exc:
        return False, None, f"io_error:{exc.strerror or exc}"
    return True, data, None


def is_stale(updated_at: Any, ttl_seconds: Any) -> bool:
    """Return ``True`` when a state payload is older than its TTL.

    Malformed or missing timestamps are treated as **stale** when a
    positive TTL is configured. A non-positive TTL (``0``, ``None``,
    ``False``) means "never stale" and returns ``False``.
    """
    try:
        ttl = float(ttl_seconds) if ttl_seconds is not None else 0.0
    except (TypeError, ValueError):
        ttl = 0.0
    if ttl <= 0:
        return False
    if not updated_at or not isinstance(updated_at, str):
        return True
    try:
        stamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
    return age > ttl


def empty_envelope(
    name: str,
    status: str = "empty",
    error: Optional[str] = None,
    privacy_mode: str = "normal",
) -> Dict[str, Any]:
    """Canonical empty envelope for a widget slot.

    Mirrors the shape produced by :func:`load_widget` so the UI can
    render a placeholder without conditional branches.
    """
    return {
        "status": status,
        "updated_at": None,
        "ttl_seconds": None,
        "privacy_mode": privacy_mode,
        "data": {},
        "error": error,
        "_widget": name,
    }


# NOTE: ``load_widget`` and ``load_aggregated_state`` are intentionally
# kept in ``server.py`` because they enforce the voice-console contract
# (top-level voice/utterance/activity/result fields) and roll up the
# ``server`` + ``poland_match_today`` fields the UI depends on. Moving
# them here would require lifting those contracts into this module
# first, which is its own commit.
