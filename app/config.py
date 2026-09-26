"""Pedro Dashboard runtime configuration.

Pure module: reads environment variables and the project VERSION file,
exposes immutable constants. No side effects, no I/O beyond reading the
VERSION file and the current process environment.

Refactor: extracted from `app/server.py` so runtime defaults, port
overrides, and version reporting live in one place. Behavior must stay
identical to the inline definitions that lived in `server.py`.

Conventions:
- `DASHBOARD_HOST` env: `127.0.0.1` or `localhost` (anything else falls
  back to loopback; LAN exposure is intentionally not supported in MVP).
- `DASHBOARD_PORT` env: integer string. Default = 17888 (lifecycle
  scripts set PEDRO_PORT=17888; this default matches it).
- `DASHBOARD_PRIVACY_MODE` env: `private` | `guest` (MVP only honors
  `private`; `guest` reserved for Etap 5).
- `DASHBOARD_LOG_LEVEL` env: standard logging level (default INFO).

The VERSION file lives at the project root (one directory above `app/`).
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APP_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = APP_DIR.parent
VERSION_FILE: Path = PROJECT_ROOT / "VERSION"
STATIC_DIR: Path = APP_DIR / "static"
STATE_DIR: Path = APP_DIR / "state"
LOGS_DIR: Path = APP_DIR / "logs"
# Operator-controlled runtime state lives outside the tracked checkout.  The
# lifecycle scripts export the same override when they launch the server.
DEFAULT_RUNTIME_DIR: Path = Path.home() / ".local" / "state" / "pedro_dashboard"
RUNTIME_DIR: Path = Path(
    os.environ.get("PEDRO_STATE_DIR", str(DEFAULT_RUNTIME_DIR))
).expanduser()
DISPLAY_CONTROL_FILE: Path = Path(
    os.environ.get("PEDRO_DISPLAY_CONTROL_FILE", str(RUNTIME_DIR / "display-control.json"))
).expanduser()

# ---------------------------------------------------------------------------
# Defaults (match runtime scripts/_lifecycle_common.sh)
# ---------------------------------------------------------------------------

DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 17888
DEFAULT_PRIVACY_MODE: str = "private"
DEFAULT_LOG_LEVEL: str = "INFO"

# ---------------------------------------------------------------------------
# Runtime values (env overrides applied)
# ---------------------------------------------------------------------------

_requested_host = os.environ.get("DASHBOARD_HOST", DEFAULT_HOST)
HOST: str = (
    _requested_host
    if _requested_host in ("127.0.0.1", "localhost")
    else DEFAULT_HOST
)

try:
    PORT: int = int(os.environ.get("DASHBOARD_PORT", str(DEFAULT_PORT)))
except ValueError:
    PORT = DEFAULT_PORT

PRIVACY_MODE: str = os.environ.get(
    "DASHBOARD_PRIVACY_MODE", DEFAULT_PRIVACY_MODE
)

LOG_LEVEL: str = os.environ.get("DASHBOARD_LOG_LEVEL", DEFAULT_LOG_LEVEL)

# ---------------------------------------------------------------------------
# Version (read from VERSION file at project root)
# ---------------------------------------------------------------------------


def read_version(default: str = "0.0.0") -> str:
    """Return trimmed VERSION file content, falling back to `default`.

    Never raises. A missing or unreadable VERSION file is not fatal —
    the dashboard reports `default` in /api/health instead of crashing.
    """
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or default
    except OSError:
        return default


VERSION: str = read_version()

__all__ = [
    "APP_DIR",
    "PROJECT_ROOT",
    "VERSION_FILE",
    "STATIC_DIR",
    "STATE_DIR",
    "LOGS_DIR",
    "DEFAULT_RUNTIME_DIR",
    "RUNTIME_DIR",
    "DISPLAY_CONTROL_FILE",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_PRIVACY_MODE",
    "DEFAULT_LOG_LEVEL",
    "HOST",
    "PORT",
    "PRIVACY_MODE",
    "LOG_LEVEL",
    "VERSION",
    "read_version",
]
