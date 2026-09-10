"""Persistent, local-only control state for the Pedro slideshow.

The kiosk is intentionally passive.  The operator-facing command writes this
small runtime file and the browser reads it through the dashboard's read-only
API.  The module has no network or process side effects; process supervision
is kept in ``scripts/pedro-display-switch.py``.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.config import DISPLAY_CONTROL_FILE

SCHEMA_VERSION = 1
DEFAULT_DASHBOARD_SECONDS = 60
DEFAULT_SLIDESHOW_SECONDS = 300
DEFAULT_PHOTO_SECONDS = 2
MAX_DASHBOARD_SECONDS = 24 * 60 * 60
MAX_SLIDESHOW_SECONDS = 24 * 60 * 60
MAX_PHOTO_SECONDS = 60

CONTROL_FIELDS = frozenset(
    {
        "schema_version",
        "enabled",
        "dashboard_seconds",
        "slideshow_seconds",
        "photo_seconds",
        "cycle_started_at",
        "generation",
        "request_id",
        "updated_at",
    }
)


class ControlStateError(ValueError):
    """Raised when a persisted control state is not safe to consume."""


@dataclass(frozen=True)
class ControlRead:
    state: dict[str, Any]
    valid: bool
    error: str | None = None


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": False,
        "dashboard_seconds": DEFAULT_DASHBOARD_SECONDS,
        "slideshow_seconds": DEFAULT_SLIDESHOW_SECONDS,
        "photo_seconds": DEFAULT_PHOTO_SECONDS,
        "cycle_started_at": None,
        "generation": 0,
        "request_id": None,
        "updated_at": None,
    }


def default_state() -> dict[str, Any]:
    """Return a fresh fail-safe OFF state."""
    return _default_state()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_seconds(value: Any, field: str, maximum: int) -> None:
    if not _is_int(value) or not 1 <= value <= maximum:
        raise ControlStateError(f"invalid_{field}")


def _validate_timestamp(value: Any, field: str, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, str) or not value.strip():
        raise ControlStateError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlStateError(f"invalid_{field}") from exc
    if parsed.tzinfo is None:
        raise ControlStateError(f"invalid_{field}")


def validate_control_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy a persisted v1 control state.

    Unknown fields, missing fields, unsafe permissions and file ownership are
    checked by :func:`read_control_state`; this function validates the JSON
    contract itself and never mutates the caller's mapping.
    """
    if not isinstance(payload, Mapping):
        raise ControlStateError("state_not_object")
    keys = set(payload)
    missing = CONTROL_FIELDS - keys
    extra = keys - CONTROL_FIELDS
    if missing:
        raise ControlStateError("missing_fields")
    if extra:
        raise ControlStateError("unknown_fields")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ControlStateError("unsupported_schema_version")
    if not isinstance(payload.get("enabled"), bool):
        raise ControlStateError("invalid_enabled")
    _validate_seconds(payload.get("dashboard_seconds"), "dashboard_seconds", MAX_DASHBOARD_SECONDS)
    _validate_seconds(payload.get("slideshow_seconds"), "slideshow_seconds", MAX_SLIDESHOW_SECONDS)
    _validate_seconds(payload.get("photo_seconds"), "photo_seconds", MAX_PHOTO_SECONDS)
    if payload.get("enabled"):
        _validate_timestamp(payload.get("cycle_started_at"), "cycle_started_at")
    elif payload.get("cycle_started_at") is not None:
        _validate_timestamp(payload.get("cycle_started_at"), "cycle_started_at")
    if not _is_int(payload.get("generation")) or payload["generation"] < 0:
        raise ControlStateError("invalid_generation")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ControlStateError("invalid_request_id")
    _validate_timestamp(payload.get("updated_at"), "updated_at")
    return dict(payload)


def _path(path: str | os.PathLike[str] | None) -> Path:
    return Path(path) if path is not None else DISPLAY_CONTROL_FILE


def _secure_existing_file(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise ControlStateError("control_file_is_symlink")
    if not stat.S_ISREG(info.st_mode):
        raise ControlStateError("control_file_not_regular")
    if info.st_uid != os.getuid():
        raise ControlStateError("control_file_wrong_owner")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ControlStateError("control_file_wrong_mode")


def read_control_state(path: str | os.PathLike[str] | None = None) -> ControlRead:
    """Read a control file, returning OFF for every invalid/missing case."""
    target = _path(path)
    try:
        _secure_existing_file(target)
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return ControlRead(validate_control_state(payload), True, None)
    except FileNotFoundError:
        return ControlRead(default_state(), False, "missing")
    except (OSError, json.JSONDecodeError, ControlStateError) as exc:
        # Deliberately return a short non-sensitive reason.  Never expose a
        # local path or raw JSON content to the browser/API.
        reason = str(exc) or "invalid"
        if not reason.startswith(("invalid_", "missing", "unknown_", "unsupported_", "state_", "control_")):
            reason = "invalid"
        return ControlRead(default_state(), False, reason)


def _timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")


def _new_state(
    *,
    enabled: bool,
    generation: int,
    cycle_started_at: str | None,
    now: datetime | None,
) -> dict[str, Any]:
    stamp = _timestamp(now)
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": enabled,
        "dashboard_seconds": DEFAULT_DASHBOARD_SECONDS,
        "slideshow_seconds": DEFAULT_SLIDESHOW_SECONDS,
        "photo_seconds": DEFAULT_PHOTO_SECONDS,
        "cycle_started_at": cycle_started_at,
        "generation": generation,
        "request_id": uuid.uuid4().hex,
        "updated_at": stamp,
    }


def transition(
    previous: Mapping[str, Any] | None,
    action: str,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    """Apply one public action and report ``(state, changed)``.

    ``on`` and ``off`` are idempotent.  Only ``restart-cycle`` creates a new
    cycle while already ON.  Invalid previous input is treated as safe OFF.
    """
    if action not in {"on", "off", "restart-cycle"}:
        raise ControlStateError("unknown_action")
    try:
        current = validate_control_state(previous or {})
    except ControlStateError:
        current = default_state()
    generation = int(current.get("generation", 0))
    enabled = bool(current.get("enabled"))

    if action == "on":
        if enabled:
            return current, False
        stamp = _timestamp(now)
        return _new_state(
            enabled=True,
            generation=generation + 1,
            cycle_started_at=stamp,
            now=now,
        ), True
    if action == "off":
        if not enabled:
            return current, False
        return _new_state(
            enabled=False,
            generation=generation + 1,
            cycle_started_at=None,
            now=now,
        ), True

    stamp = _timestamp(now)
    return _new_state(
        enabled=True,
        generation=generation + 1,
        cycle_started_at=stamp,
        now=now,
    ), True


def write_control_state(
    payload: Mapping[str, Any],
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Atomically write a validated 0600 control state."""
    target = _path(path)
    state = validate_control_state(payload)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    _secure_existing_file(target)

    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            os.fchmod(handle.fileno(), 0o600)
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        os.chmod(target, 0o600)
        try:
            dir_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return state


def apply_action(
    action: str,
    path: str | os.PathLike[str] | None = None,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], bool, ControlRead]:
    """Read, transition and atomically persist one public action."""
    current = read_control_state(path)
    state, changed = transition(current.state if current.valid else default_state(), action, now=now)
    if changed:
        state = write_control_state(state, path)
    return state, changed, current


def control_envelope(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Return the read-only API envelope consumed by the browser."""
    result = read_control_state(path)
    state = result.state
    return {
        "status": "ok" if result.valid and state["enabled"] else "off",
        "updated_at": state.get("updated_at"),
        "ttl_seconds": None,
        "data": state,
        "valid": result.valid,
        "error": None if result.valid or result.error == "missing" else "invalid_display_control",
        "_widget": "display_control",
    }


__all__ = [
    "CONTROL_FIELDS",
    "ControlRead",
    "ControlStateError",
    "DEFAULT_DASHBOARD_SECONDS",
    "DEFAULT_PHOTO_SECONDS",
    "DEFAULT_SLIDESHOW_SECONDS",
    "SCHEMA_VERSION",
    "apply_action",
    "control_envelope",
    "default_state",
    "read_control_state",
    "transition",
    "validate_control_state",
    "write_control_state",
]
