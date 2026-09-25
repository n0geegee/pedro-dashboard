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

# Per-probe wall-clock cap. A hung probe (DNS stall, stuck Google API call)
# must not freeze the whole refresh loop and turn every widget stale.
PROBE_TIMEOUT="${PEDRO_PROBE_TIMEOUT:-60}"
PHOTOS_PROBE_TIMEOUT="${PEDRO_PHOTOS_PROBE_TIMEOUT:-600}"

# Minimum seconds between runs of network probes whose sources change slowly.
# Freshness is judged by the mtime of the probe's output file, so a probe
# that failed without writing is simply retried on the next cycle. 0 = every
# cycle. All values stay well below each widget's ttl_seconds.
declare -A PROBE_OUT=(
  [refresh-weather-status.py]=weather.json
  [refresh-kamila-calendar.py]=calendar.json
  [refresh-vnl-volleyball.py]=volleyball.json
)
declare -A PROBE_MIN_AGE=(
  [refresh-weather-status.py]="${PEDRO_WEATHER_MIN_AGE:-300}"
  [refresh-kamila-calendar.py]="${PEDRO_CALENDAR_MIN_AGE:-120}"
  [refresh-vnl-volleyball.py]="${PEDRO_VNL_MIN_AGE:-300}"
)

# True when the probe's output is younger than its minimum refresh age.
# Error envelopes never count as fresh, so failures keep retrying each cycle.
probe_is_fresh() {
  local probe="$1" out min_age path mtime
  out="${PROBE_OUT[$probe]:-}"
  min_age="${PROBE_MIN_AGE[$probe]:-0}"
  [[ -n "$out" && "$min_age" -gt 0 ]] || return 1
  path="$PEDRO_PROJECT_ROOT/app/state/$out"
  mtime="$(stat -c %Y "$path" 2>/dev/null)" || return 1
  (( $(date +%s) - mtime < min_age )) || return 1
  ! grep -q '^  "status": "error"' "$path"
}

# Baseline: keeps not-yet-connected display widgets fresh instead of stale.
# Widgets that have a live probe are skipped, otherwise every cycle would
# briefly publish mock data (and keep showing it as "ok" if the probe died).
mock_skip=()
[[ -f "$SCRIPT_DIR/refresh-system-status.py" ]] && mock_skip+=(system.json)
[[ -f "$SCRIPT_DIR/refresh-hermes-status.py" ]] && mock_skip+=(hermes.json)
[[ -f "$SCRIPT_DIR/refresh-openviking-status.py" ]] && mock_skip+=(openviking.json)
if [[ -f "$SCRIPT_DIR/write-mock-state.py" ]]; then
  "$PY_BIN" "$SCRIPT_DIR/write-mock-state.py" --skip "$(IFS=,; echo "${mock_skip[*]}")" >/dev/null || status=$?
fi

# Live probes: overwrite mock baseline with real operational/user state.
# refresh-photos-slideshow.py is skipped here when photos-rotator.sh is
# already running, because that rotator calls the probe every slide_seconds
# (5s) on its own loop. Running it from both loops at the same time
# produces a race on media.json.slideshow.current that makes the kiosk
# occasionally skip a photo. If the rotator is not running, the photos
# probe still runs here at the 20s state-refresher cadence so the kiosk
# is not stuck on a stale image.
PHOTOS_PID_FILE="$PEDRO_RUN_DIR/photos-rotator.pid"
photos_owned=0
if [[ -f "$PHOTOS_PID_FILE" ]]; then
  photos_pid="$(tr -d '[:space:]' < "$PHOTOS_PID_FILE" 2>/dev/null || true)"
  if [[ "$photos_pid" =~ ^[0-9]+$ ]] && kill -0 "$photos_pid" 2>/dev/null; then
    photos_owned=1
  fi
fi
for probe in refresh-system-status.py refresh-hermes-status.py refresh-openviking-status.py refresh-season-skin.py refresh-weather-status.py refresh-route-status.py refresh-polsat-status.py refresh-photos-slideshow.py refresh-kamila-calendar.py refresh-vnl-volleyball.py; do
  if [[ -f "$SCRIPT_DIR/$probe" ]]; then
    if [[ "$probe" == "refresh-photos-slideshow.py" ]] && [[ "$photos_owned" == "1" ]]; then
      continue
    fi
    if probe_is_fresh "$probe"; then
      continue
    fi
    probe_py="$PY_BIN"
    if [[ "$probe" == "refresh-kamila-calendar.py" ]]; then
      probe_py="$HERMES_PY_BIN"
    fi
    probe_timeout="$PROBE_TIMEOUT"
    if [[ "$probe" == "refresh-photos-slideshow.py" ]]; then
      probe_timeout="$PHOTOS_PROBE_TIMEOUT"
    fi
    rc=0
    timeout -k 5 "$probe_timeout" "$probe_py" "$SCRIPT_DIR/$probe" >/dev/null || rc=$?
    if [[ "$rc" == "124" || "$rc" == "137" ]]; then
      printf '[%s] probe %s killed after %ss timeout\n' "$(pedro_log_ts)" "$probe" "$probe_timeout" >&2
    fi
    [[ "$rc" == "0" ]] || status=$rc
  fi
done

# Voice console idle heartbeat (v1.2). Uses the dedicated voice venv so
# we do not pollute the system python with python-xlib. If the voice
# daemon is alive it owns the file; if it crashed, this repaints idle.
if [[ -x "${PEDRO_VOICE_PY_BIN:-/nonexistent}" ]] && [[ -f "$SCRIPT_DIR/refresh-voice-console.py" ]]; then
  "$PEDRO_VOICE_PY_BIN" "$SCRIPT_DIR/refresh-voice-console.py" >/dev/null || status=$?
fi

exit "$status"
