#!/usr/bin/env python3
"""Shared helpers for Pedro Dashboard status probes (Etap 3).

Internal module. Not executed directly. Functions are intentionally simple,
timeout-safe (no blocking I/O without a bound), and write JSON atomically so
the dashboard server can never see a half-written file.

Privacy contract:
  * Probes MUST NOT include raw log text, session content, tokens, or
    credential paths. Public operational facts only.
  * On any failure we still write a JSON file with status="error" and a
    small structured error payload. The dashboard treats that as a degraded
    widget instead of a missing file.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
DEFAULT_STATE_DIR = APP_DIR / "state"
PRIVACY_MODE = os.environ.get("DASHBOARD_PRIVACY_MODE", "private")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path: Path, payload: dict) -> None:
    """Atomic JSON write: temp file in same dir + flush + os.replace().

    Never leaves a half-written JSON in the final path. Safe to call from
    probes that are interrupted by a timeout signal: the final file will be
    either the previous good payload or the new full payload.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            # Some filesystems (e.g. virtual mounts) reject fsync; we still
            # did flush(), so the bytes are at least in the OS buffers.
            pass
    os.replace(tmp, path)


def envelope(widget: str, status: str, ttl: int, data: dict, error: dict | None = None) -> dict:
    """Build a widget envelope in the same shape write-mock-state.py uses.

    `data` is the public operational payload. `error` is a tiny structured
    error descriptor (code + short public message) and never contains raw
    logs, tokens, or session text.
    """
    return {
        "status": status,
        "updated_at": now_iso(),
        "ttl_seconds": ttl,
        "privacy_mode": PRIVACY_MODE,
        "data": data,
        "error": error,
    }


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def write_error_envelope(state_dir: Path, name: str, ttl: int, code: str, message: str) -> Path:
    """Always-success writer for an error widget. Caller uses this to keep
    state files present even when the probe itself failed."""
    payload = envelope(name, "error", ttl, {}, error={"code": code, "message_public": message})
    out = state_dir / f"{name}.json"
    atomic_write(out, payload)
    return out


def resolve_state_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return DEFAULT_STATE_DIR


def parse_args_state_dir(description: str):
    import argparse

    p = argparse.ArgumentParser(description=description)
    p.add_argument(
        "--out",
        default=None,
        help="output state directory (default: app/state/ next to the project root)",
    )
    p.add_argument(
        "--ttl",
        type=int,
        default=None,
        help="override ttl_seconds written into the envelope",
    )
    return p


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Hint for tests / callers
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 17890

if __name__ == "__main__":  # pragma: no cover - not a runnable script
    sys.stderr.write("This is a helper module, not a runnable script.\n")
    raise SystemExit(64)
