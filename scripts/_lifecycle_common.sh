#!/usr/bin/env bash
# Pedro Dashboard — no-systemd lifecycle helper.
# Shared paths and helpers. Source this from the other scripts:
#   source "$(dirname "${BASH_SOURCE[0]}")/_lifecycle_common.sh"
#
# Conventions:
#   * State dir: $PEDRO_STATE_DIR (default: ~/.local/state/pedro_dashboard)
#   * Logs:      $PEDRO_STATE_DIR/logs/
#   * PIDs:      $PEDRO_STATE_DIR/run/
#   * Bind:      127.0.0.1:17888 (PEDRO_HOST / PEDRO_PORT override)
#   * No systemctl, no journalctl. Logs are plain files; the dashboard
#     server also keeps its own log at app/logs/server.log for app-internal
#     diagnostics.
#
# All public functions are prefixed `pedro_` to avoid clashing with anything
# the operator might have in their shell rc.

# Be conservative: -u catches typos, -o pipefail catches failed pipes.
# We do NOT set -e globally; the calling script decides when to abort.
set -uo pipefail

# --- paths ----------------------------------------------------------------

PEDRO_HOME="${PEDRO_HOME:-$HOME}"
PEDRO_STATE_DIR="${PEDRO_STATE_DIR:-$PEDRO_HOME/.local/state/pedro_dashboard}"
PEDRO_LOG_DIR="${PEDRO_LOG_DIR:-$PEDRO_STATE_DIR/logs}"
PEDRO_RUN_DIR="${PEDRO_RUN_DIR:-$PEDRO_STATE_DIR/run}"
PEDRO_CHROME_PROFILE_DIR="${PEDRO_CHROME_PROFILE_DIR:-$PEDRO_STATE_DIR/chrome-profile}"

PEDRO_HOST="${PEDRO_HOST:-127.0.0.1}"
PEDRO_PORT="${PEDRO_PORT:-17888}"
PEDRO_HEALTH_URL="http://${PEDRO_HOST}:${PEDRO_PORT}/api/health"

# Project root is the parent of the scripts/ directory this file lives in.
# Allow the operator to override (handy for tests / out-of-tree runs).
if [[ -n "${PEDRO_PROJECT_ROOT:-}" ]]; then
  : # keep
elif [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  PEDRO_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
else
  PEDRO_PROJECT_ROOT="/home/imac-hermes/projects/pedro_dashboard"
fi

PEDRO_SERVER_CMD="${PEDRO_SERVER_CMD:-python3}"
PEDRO_SERVER_ARGS_DEFAULT=("$PEDRO_PROJECT_ROOT/app/server.py")
PEDRO_PID_FILE="${PEDRO_PID_FILE:-$PEDRO_RUN_DIR/dashboard.pid}"
PEDRO_KIOSK_PID_FILE="${PEDRO_KIOSK_PID_FILE:-$PEDRO_RUN_DIR/kiosk.pid}"
PEDRO_WATCHDOG_PID_FILE="${PEDRO_WATCHDOG_PID_FILE:-$PEDRO_RUN_DIR/watchdog.pid}"

PEDRO_LOG_FILE="${PEDRO_LOG_FILE:-$PEDRO_LOG_DIR/dashboard.out.log}"
PEDRO_LOG_ERR_FILE="${PEDRO_LOG_ERR_FILE:-$PEDRO_LOG_DIR/dashboard.err.log}"
PEDRO_KIOSK_LOG_FILE="${PEDRO_KIOSK_LOG_FILE:-$PEDRO_LOG_DIR/kiosk.out.log}"
PEDRO_KIOSK_LOG_ERR_FILE="${PEDRO_KIOSK_LOG_ERR_FILE:-$PEDRO_LOG_DIR/kiosk.err.log}"
PEDRO_WATCHDOG_LOG_FILE="${PEDRO_WATCHDOG_LOG_FILE:-$PEDRO_LOG_DIR/watchdog.log}"
PEDRO_AUTOSTART_LOG_FILE="${PEDRO_AUTOSTART_LOG_FILE:-$PEDRO_LOG_DIR/install-autostart.log}"

PEDRO_XDG_AUTOSTART_DIR="${PEDRO_XDG_AUTOSTART_DIR:-$PEDRO_HOME/.config/autostart}"
PEDRO_AUTOSTART_SERVER_FILE="${PEDRO_AUTOSTART_SERVER_FILE:-$PEDRO_XDG_AUTOSTART_DIR/pedro-dashboard-server.desktop}"
PEDRO_AUTOSTART_KIOSK_FILE="${PEDRO_AUTOSTART_KIOSK_FILE:-$PEDRO_XDG_AUTOSTART_DIR/pedro-dashboard-kiosk.desktop}"

# Voice subsystem (v1.2 push-to-talk "hey pedro")
PEDRO_VOICE_PY_BIN="${PEDRO_VOICE_PY_BIN:-$PEDRO_PROJECT_ROOT/.venv-voice/bin/python}"
PEDRO_VOICE_DAEMON_SCRIPT="${PEDRO_VOICE_DAEMON_SCRIPT:-$PEDRO_PROJECT_ROOT/scripts/pedro_voice_daemon.py}"
PEDRO_VOICE_DAEMON_PID_FILE="${PEDRO_VOICE_DAEMON_PID_FILE:-$PEDRO_RUN_DIR/voice_daemon.pid}"
PEDRO_VOICE_DAEMON_LOG_FILE="${PEDRO_VOICE_DAEMON_LOG_FILE:-$PEDRO_LOG_DIR/voice_daemon.log}"
PEDRO_VOICE_TRIGGER_KEYCODE="${PEDRO_VOICE_TRIGGER_KEYCODE:-65}"  # Space
PEDRO_MIC_DEVICE="${PEDRO_MIC_DEVICE:-plughw:0,2}"
PEDRO_PRIVACY_FILE="${PEDRO_PRIVACY_FILE:-$PEDRO_STATE_DIR/privacy_mode}"
PEDRO_AUTOSTART_VOICE_FILE="${PEDRO_AUTOSTART_VOICE_FILE:-$PEDRO_XDG_AUTOSTART_DIR/pedro-voice-daemon.desktop}"

# Voice subsystem v1.4 — always-listening "hey pedro" KWS daemon
# (Vosk streaming STT → Gemini command STT → runner → espeak-ng TTS)
# Replaces v1.3 push-to-talk on the iMac because that kiosk has no keyboard.
PEDRO_VOICE_KWS_SCRIPT="${PEDRO_VOICE_KWS_SCRIPT:-$PEDRO_PROJECT_ROOT/scripts/pedro_voice_kws.py}"
PEDRO_VOICE_KWS_PID_FILE="${PEDRO_VOICE_KWS_PID_FILE:-$PEDRO_RUN_DIR/voice_kws.pid}"
PEDRO_VOICE_KWS_LOG_FILE="${PEDRO_VOICE_KWS_LOG_FILE:-$PEDRO_LOG_DIR/voice_kws.log}"
PEDRO_VOSK_MODEL="${PEDRO_VOSK_MODEL:-$HOME/.local/share/vosk/models/small-pl}"
PEDRO_VOICE_KWS_COMMAND_SECONDS="${PEDRO_VOICE_KWS_COMMAND_SECONDS:-4.0}"
PEDRO_AUTOSTART_VOICE_KWS_FILE="${PEDRO_AUTOSTART_VOICE_KWS_FILE:-$PEDRO_XDG_AUTOSTART_DIR/pedro-voice-kws.desktop}"

# Photos slideshow tuning (scripts/refresh-photos-slideshow.py)
# Override the 30 min default; user wants fresh photos on a 5 min cycle
# so newly added Google Photos items show up quickly on the kiosk.
PEDRO_GOOGLE_PHOTOS_REFRESH_SECONDS="${PEDRO_GOOGLE_PHOTOS_REFRESH_SECONDS:-300}"
export PEDRO_GOOGLE_PHOTOS_REFRESH_SECONDS
# User's shared album has been growing — 191 items on 2026-06-16,
# ~246 by mid-day. Default cap (80) silently dropped most of them.
# Raise to 300 for headroom; user can keep adding without re-tuning.
PEDRO_GOOGLE_PHOTOS_MAX_IMAGES="${PEDRO_GOOGLE_PHOTOS_MAX_IMAGES:-300}"
export PEDRO_GOOGLE_PHOTOS_MAX_IMAGES
# User wants 5 s/photo so the full 220-item album cycles in ~18 min
# instead of ~165 min. Default in script is 45 s.
PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS="${PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS:-5}"
export PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS

# --- helpers --------------------------------------------------------------

pedro_log_ts() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

pedro_log() {
  # Always log to the lifecycle logfile. Stdout is left to the calling
  # script so the operator sees status updates on the terminal.
  local msg="$*"
  mkdir -p "$PEDRO_LOG_DIR" 2>/dev/null || true
  printf '[%s] %s\n' "$(pedro_log_ts)" "$msg" >> "$PEDRO_WATCHDOG_LOG_FILE" 2>/dev/null || true
}

pedro_ensure_dirs() {
  mkdir -p "$PEDRO_LOG_DIR" "$PEDRO_RUN_DIR" "$PEDRO_CHROME_PROFILE_DIR" 2>/dev/null || true
}

pedro_pid_alive() {
  # $1 = pid file. Echo "1" if pid file exists, points to an integer, and
  # that pid is alive. Echo "0" otherwise. Never raises.
  local pidfile="${1:-}"
  [[ -n "$pidfile" && -f "$pidfile" ]] || { echo 0; return 0; }
  local pid
  pid="$(tr -d '[:space:]' < "$pidfile" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] || { echo 0; return 0; }
  if kill -0 "$pid" 2>/dev/null; then
    echo 1
  else
    echo 0
  fi
}

pedro_pid_clean_stale() {
  # Remove a pid file if the pid is no longer alive. Idempotent.
  local pidfile="${1:-}"
  [[ -n "$pidfile" ]] || return 0
  if [[ -f "$pidfile" ]] && [[ "$(pedro_pid_alive "$pidfile")" == "0" ]]; then
    rm -f "$pidfile" 2>/dev/null || true
  fi
}

pedro_pid_cmdline() {
  # $1 pid. Print cmdline with NULs converted to spaces. Empty on failure.
  local pid="${1:-}"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
}

pedro_pid_matches_all() {
  # $1 pid, remaining args are fixed substrings required in /proc/PID/cmdline.
  local pid="${1:-}"
  shift || true
  [[ "$pid" =~ ^[0-9]+$ ]] || { echo 0; return 0; }
  kill -0 "$pid" 2>/dev/null || { echo 0; return 0; }
  local cmd
  cmd="$(pedro_pid_cmdline "$pid")"
  [[ -n "$cmd" ]] || { echo 0; return 0; }
  local needle
  for needle in "$@"; do
    [[ "$cmd" == *"$needle"* ]] || { echo 0; return 0; }
  done
  echo 1
}

pedro_port_listening() {
  # $1 host, $2 port. Echo "1" if ss reports a LISTEN, "0" otherwise.
  # Uses `ss` (preferred) with a `bash /dev/tcp` fallback if `ss` is missing.
  local host="${1:-127.0.0.1}"
  local port="${2:-0}"
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -E "^((\\*|0\\.0\\.0\\.0|\\[::\\]|::):${port}|${host}:${port})$" >/dev/null 2>&1; then
      echo 1
    else
      echo 0
    fi
    return 0
  fi
  # Fallback: connect()/close. Cheap and good enough for a single port.
  if (exec 3<>"/dev/tcp/${host}/${port}") 2>/dev/null; then
    exec 3<&- 3>&- 2>/dev/null || true
    echo 1
  else
    echo 0
  fi
}

pedro_http_health() {
  # $1 url, $2 timeout seconds (default 2). Echo "1" on HTTP 200 within
  # timeout, "0" otherwise. Never raises.
  local url="${1:-}"
  local timeout_s="${2:-2}"
  [[ -n "$url" ]] || { echo 0; return 0; }
  if ! command -v curl >/dev/null 2>&1; then
    echo 0
    return 0
  fi
  local code
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time "$timeout_s" "$url" 2>/dev/null || echo 000)"
  if [[ "$code" == "200" ]]; then
    echo 1
  else
    echo 0
  fi
}

pedro_voice_daemon_alive() {
  # Echo "1" if the voice daemon PID file exists and points to a live
  # process, "0" otherwise. Mirrors pedro_pid_alive but specialised
  # for the voice subsystem (we want the helper name to read well in
  # watchdog and start scripts).
  local pidfile="${PEDRO_VOICE_DAEMON_PID_FILE:-}"
  if [[ -z "$pidfile" ]]; then
    echo 0
    return 0
  fi
  if [[ ! -f "$pidfile" ]]; then
    echo 0
    return 0
  fi
  local pid
  pid="$(tr -d '[:space:]' < "$pidfile" 2>/dev/null || true)"
  if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    echo 0
    return 0
  fi
  if kill -0 "$pid" 2>/dev/null; then
    echo 1
  else
    echo 0
  fi
}

pedro_voice_kws_alive() {
  # Same shape as pedro_voice_daemon_alive but for the v1.4 KWS daemon.
  # The KWS daemon also writes the legacy voice_daemon.pid alias so the
  # v1.3 refresher does not race us; this helper prefers the canonical
  # voice_kws.pid and falls back to the legacy alias.
  local pidfile="${PEDRO_VOICE_KWS_PID_FILE:-}"
  if [[ -n "$pidfile" ]] && [[ -f "$pidfile" ]]; then
    local pid
    pid="$(tr -d '[:space:]' < "$pidfile" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      echo 1
      return 0
    fi
  fi
  # Fallback: legacy voice_daemon.pid (set as alias by KWS daemon)
  pedro_voice_daemon_alive
}

pedro_display_works() {
  # Echo "1" if the configured DISPLAY (or :0 fallback) accepts an X
  # connection. Used by start-kiosk.sh to avoid spawning Chrome against a
  # dead DISPLAY. We do NOT actually open an X11 connection here; we use
  # the same cheap Unix-socket probe as refresh-system-status.py via
  # python3 -c, since it is already part of the runtime and we want to
  # keep this file pure bash + stdlib-aware.
  local display="${DISPLAY:-}"
  if [[ -z "$display" ]]; then
    display=":0"
  fi
  # Headless and explicit disable short-circuits.
  case "$display" in
    "") echo 0; return 0 ;;
  esac
  # Extract the display number.
  local after="${display#*:}"
  local num="${after%%.*}"
  if ! [[ "$num" =~ ^[0-9]+$ ]]; then
    echo 0
    return 0
  fi
  local sock="/tmp/.X11-unix/X${num}"
  if [[ -S "$sock" ]]; then
    echo 1
  else
    echo 0
  fi
}
