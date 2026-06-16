#!/usr/bin/env bash
# Pedro Dashboard — refresh all state files once.
#
# Keeps UI stable while data sources are progressively connected:
# 1) write mock baseline for visual-only widgets still awaiting credentials/API decisions;
# 2) overwrite core operational widgets with real probes where available.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

PY_BIN="${PEDRO_SERVER_CMD:-python3}"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  PY_BIN=/usr/bin/python3
fi
HERMES_PY_BIN="${HERMES_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python}"
if [[ ! -x "$HERMES_PY_BIN" ]]; then
  HERMES_PY_BIN="$PY_BIN"
fi

cd "$PEDRO_PROJECT_ROOT" || exit 70
pedro_ensure_dirs

# Refresher often runs from SSH/no-systemd without DISPLAY in the environment.
# The iMac kiosk target is the built-in LVDS screen on :0; set this fallback so
# system.json reports display reachability correctly while still allowing an
# operator override.
export DISPLAY="${DISPLAY:-:0}"

# Load local Hermes/Pedro credentials for live probes, without printing values.
# This is needed for GOOGLE_MAPS_API_KEY in the route probe when the refresher
# runs as a detached no-systemd process rather than through a Hermes terminal.
if [[ -f "$HOME/.hermes/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$HOME/.hermes/.env"
  set +a
fi

status=0

# Baseline: keeps not-yet-connected display widgets fresh instead of stale.
if [[ -f "$SCRIPT_DIR/write-mock-state.py" ]]; then
  "$PY_BIN" "$SCRIPT_DIR/write-mock-state.py" >/dev/null || status=$?
fi

# Live probes: overwrite mock baseline with real operational/user state.
for probe in refresh-system-status.py refresh-hermes-status.py refresh-openviking-status.py refresh-season-skin.py refresh-weather-status.py refresh-route-status.py refresh-polsat-status.py refresh-photos-slideshow.py refresh-kamila-calendar.py refresh-match-calendar.py; do
  if [[ -f "$SCRIPT_DIR/$probe" ]]; then
    probe_py="$PY_BIN"
    if [[ "$probe" == "refresh-kamila-calendar.py" ]]; then
      probe_py="$HERMES_PY_BIN"
    fi
    "$probe_py" "$SCRIPT_DIR/$probe" >/dev/null || status=$?
  fi
done

exit "$status"
