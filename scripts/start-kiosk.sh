#!/usr/bin/env bash
# Pedro Dashboard — start a Chrome kiosk window pointing at the dashboard.
#
# Contract (per task instructions):
#   * Never forcibly launch Chrome when DISPLAY does not work. If the X
#     socket is not reachable, exit 0 with a clear note — the operator
#     can run this manually from their desktop session.
#   * Use a dedicated user-data-dir under $PEDRO_CHROME_PROFILE_DIR.
#   * No systemd / journalctl.
#
# Usage:
#   scripts/start-kiosk.sh
#   scripts/start-kiosk.sh --url http://127.0.0.1:17890/
#   scripts/start-kiosk.sh --stop   # stop an existing kiosk
#   scripts/start-kiosk.sh --status # report kiosk state, do not start
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

URL="http://${PEDRO_HOST}:${PEDRO_PORT}/"
CHROME_BIN="${CHROME_BIN:-/usr/bin/google-chrome}"
ACTION="start"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url|-u) URL="$2"; shift 2 ;;
    --chrome) CHROME_BIN="$2"; shift 2 ;;
    --stop) ACTION="stop"; shift ;;
    --status) ACTION="status"; shift ;;
    --help|-h)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

pedro_ensure_dirs
mkdir -p "$PEDRO_CHROME_PROFILE_DIR" 2>/dev/null || true

kiosk_pid=""
if [[ -f "$PEDRO_KIOSK_PID_FILE" ]]; then
  kiosk_pid="$(tr -d '[:space:]' < "$PEDRO_KIOSK_PID_FILE" 2>/dev/null || true)"
fi

case "$ACTION" in
  stop)
    if [[ -n "$kiosk_pid" ]] && [[ "$kiosk_pid" =~ ^[0-9]+$ ]] && kill -0 "$kiosk_pid" 2>/dev/null; then
      if [[ "$(pedro_pid_matches_all "$kiosk_pid" "$PEDRO_CHROME_PROFILE_DIR" "$URL")" != "1" ]]; then
        echo "refusing to stop pid=$kiosk_pid: not this Pedro kiosk"
        pedro_log "start-kiosk.sh: refused non-kiosk pid=$kiosk_pid cmd=$(pedro_pid_cmdline "$kiosk_pid")"
        rm -f "$PEDRO_KIOSK_PID_FILE" 2>/dev/null || true
        exit 1
      fi
      kill -TERM "$kiosk_pid" 2>/dev/null || true
      pedro_log "start-kiosk.sh: SIGTERM -> $kiosk_pid"
      for _ in $(seq 1 25); do
        sleep 0.2
        if ! kill -0 "$kiosk_pid" 2>/dev/null; then break; fi
      done
      if kill -0 "$kiosk_pid" 2>/dev/null; then
        kill -KILL "$kiosk_pid" 2>/dev/null || true
        pedro_log "start-kiosk.sh: SIGKILL -> $kiosk_pid"
      fi
    fi
    rm -f "$PEDRO_KIOSK_PID_FILE" 2>/dev/null || true
    echo "kiosk stopped"
    exit 0
    ;;
  status)
    if [[ -n "$kiosk_pid" ]] && [[ "$kiosk_pid" =~ ^[0-9]+$ ]] && [[ "$(pedro_pid_matches_all "$kiosk_pid" "$PEDRO_CHROME_PROFILE_DIR" "$URL")" == "1" ]]; then
      echo "kiosk running: pid=$kiosk_pid url=$URL chrome=$CHROME_BIN"
      exit 0
    fi
    echo "kiosk not running"
    exit 1
    ;;
esac

# Idempotency: kiosk already up?
if [[ -n "$kiosk_pid" ]] && [[ "$kiosk_pid" =~ ^[0-9]+$ ]] && [[ "$(pedro_pid_matches_all "$kiosk_pid" "$PEDRO_CHROME_PROFILE_DIR" "$URL")" == "1" ]]; then
  echo "kiosk already running (pid=$kiosk_pid)"
  pedro_log "start-kiosk.sh: already running pid=$kiosk_pid"
  exit 0
fi
pedro_pid_clean_stale "$PEDRO_KIOSK_PID_FILE"

# DISPLAY gate. Do NOT forcibly launch Chrome if X is not reachable.
if [[ "$(pedro_display_works)" != "1" ]]; then
  echo "DISPLAY not reachable (current DISPLAY='${DISPLAY:-}'); skipping kiosk launch."
  echo "  hint: run from a desktop session, or set DISPLAY=:0 and ensure X is up."
  pedro_log "start-kiosk.sh: DISPLAY unreachable; skipping (DISPLAY='${DISPLAY:-}')"
  exit 0
fi

# Make sure the dashboard is up before pointing Chrome at it. We do not
# start it from here (that's start-dashboard.sh / watchdog-dashboard.sh's
# job); we just refuse to launch kiosk against a dead backend.
if [[ "$(pedro_http_health "$PEDRO_HEALTH_URL" 1)" != "1" ]]; then
  echo "dashboard health not OK at $PEDRO_HEALTH_URL; start it with scripts/start-dashboard.sh first"
  pedro_log "start-kiosk.sh: dashboard health not ok; refusing to launch kiosk"
  exit 75
fi

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "chrome not found at $CHROME_BIN; install google-chrome or set CHROME_BIN" >&2
  pedro_log "start-kiosk.sh: chrome not found at $CHROME_BIN"
  exit 73
fi

: > "$PEDRO_KIOSK_LOG_FILE"
: > "$PEDRO_KIOSK_LOG_ERR_FILE"

# Use --no-first-run and a dedicated profile to avoid polluting the user's
# default Chrome state. --kiosk opens full-screen; we do NOT add
# --noerrdialogs / --disable-session-crashed-bubble in this MVP — the
# operator can layer them later if a kiosk session is real.
setsid "$CHROME_BIN" \
  --kiosk "$URL" \
  --no-first-run \
  --disable-background-timer-throttling \
  --disable-renderer-backgrounding \
  --disable-backgrounding-occluded-windows \
  --disable-features=CalculateNativeWinOcclusion \
  --disable-gpu \
  --disable-accelerated-2d-canvas \
  --user-data-dir="$PEDRO_CHROME_PROFILE_DIR" \
  >>"$PEDRO_KIOSK_LOG_FILE" 2>>"$PEDRO_KIOSK_LOG_ERR_FILE" </dev/null &

KIOSK_PID=$!
echo "$KIOSK_PID" > "$PEDRO_KIOSK_PID_FILE"
pedro_log "start-kiosk.sh: spawned pid=$KIOSK_PID url=$URL"

# Give Chrome a moment to start, but do not block the operator.
sleep 0.5
if kill -0 "$KIOSK_PID" 2>/dev/null; then
  echo "kiosk started (pid=$KIOSK_PID url=$URL profile=$PEDRO_CHROME_PROFILE_DIR)"
  exit 0
fi

echo "ERROR: chrome exited immediately; see $PEDRO_KIOSK_LOG_ERR_FILE" >&2
pedro_log "start-kiosk.sh: chrome exited immediately"
rm -f "$PEDRO_KIOSK_PID_FILE" 2>/dev/null || true
exit 74
