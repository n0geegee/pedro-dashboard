#!/usr/bin/env bash
# Pedro Dashboard — slideshow rotator loop.
#
# Calls refresh-photos-slideshow.py every PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS
# (default 5s) so the kiosk gets a fresh image_url on every poll cycle.
# The Python script itself advances `pick_image` by one slot per call (it
# remembers the previous index in media.json.slideshow.current), so calling
# this loop at slide-second cadence gives "next image every N seconds" —
# not "image index = (time / N) mod total" which would skip 3-4 images
# per refresh on the default 20s state-refresher cadence.
#
# Why not just shorten the state-refresher interval? The state refresher
# fans out to many other probes (system, hermes, weather, route, calendar,
# volleyball, polsat) and 20s is the right cadence for those. A separate
# fast loop for photos keeps the cost low and the rotation snappy.
#
# Usage:
#   scripts/photos-rotator.sh --start        # daemonise
#   scripts/photos-rotator.sh --stop
#   scripts/photos-rotator.sh --status
#   scripts/photos-rotator.sh --loop --interval 5   # foreground loop
#   PEDRO_PHOTOS_ROTATOR_INTERVAL=5 scripts/photos-rotator.sh --start
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

PROBE="$SCRIPT_DIR/refresh-photos-slideshow.py"
PID_FILE="$PEDRO_RUN_DIR/photos-rotator.pid"
LOG_FILE="$PEDRO_LOG_DIR/photos-rotator.log"

INTERVAL="${PEDRO_PHOTOS_ROTATOR_INTERVAL:-${PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS:-5}}"
ACTION="status"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --start) ACTION="start"; shift ;;
    --stop)  ACTION="stop";  shift ;;
    --status) ACTION="status"; shift ;;
    --loop)  ACTION="loop";  shift ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,22p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

pedro_ensure_dirs

# _lifecycle_common.sh does not export PY_BIN; it exposes PEDRO_SERVER_CMD
# (default "python3") which is what refresh-all-state.sh also uses. We
# resolve it the same way here so this script works regardless of how the
# user sourced the lifecycle env.
PY_BIN="${PEDRO_SERVER_CMD:-python3}"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  PY_BIN=/usr/bin/python3
fi

is_ours() {
  local pid="${1:-}"
  [[ "$pid" =~ ^[0-9]+$ ]] || { echo 0; return 0; }
  if [[ "$(pedro_pid_matches_all "$pid" "photos-rotator.sh" "--loop")" == "1" ]]; then
    echo 1
  else
    echo 0
  fi
}

read_pid() {
  [[ -f "$PID_FILE" ]] || { echo ""; return 0; }
  tr -d '[:space:]' < "$PID_FILE" 2>/dev/null || true
}

case "$ACTION" in
  status)
    pid="$(read_pid)"
    if [[ "$(is_ours "$pid")" == "1" ]]; then
      echo "photos rotator running: pid=$pid interval=${INTERVAL}s log=$LOG_FILE"
      exit 0
    fi
    echo "photos rotator stopped"
    exit 1
    ;;
  stop)
    pid="$(read_pid)"
    if [[ -z "$pid" ]] || [[ "$(is_ours "$pid")" == "0" ]]; then
      rm -f "$PID_FILE"
      echo "photos rotator already stopped"
      exit 0
    fi
    if kill "$pid" 2>/dev/null; then
      # give the loop a moment to write the lock release, then clean up
      for _ in 1 2 3 4 5; do
        [[ "$(is_ours "$pid")" == "1" ]] || break
        sleep 1
      done
      rm -f "$PID_FILE"
      echo "photos rotator stopped (pid=$pid)"
      exit 0
    fi
    rm -f "$PID_FILE"
    echo "photos rotator: kill failed for pid=$pid, removed pidfile"
    exit 1
    ;;
  start)
    pid="$(read_pid)"
    if [[ "$(is_ours "$pid")" == "1" ]]; then
      echo "photos rotator already running: pid=$pid interval=${INTERVAL}s"
      exit 0
    fi
    rm -f "$PID_FILE"
    setsid "$0" --loop --interval "$INTERVAL" >> "$LOG_FILE" 2>&1 </dev/null &
    newpid=$!
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      [[ "$(is_ours "$newpid")" == "1" ]] && break
      sleep 0.3
    done
    if [[ "$(is_ours "$newpid")" == "1" ]]; then
      echo "photos rotator started (pid=$newpid interval=${INTERVAL}s log=$LOG_FILE)"
      exit 0
    fi
    echo "photos rotator: failed to start (see $LOG_FILE)" >&2
    tail -20 "$LOG_FILE" >&2 || true
    exit 1
    ;;
  loop)
    # foreground loop. Detach via setsid in the --start case above.
    echo "$BASHPID" > "$PID_FILE"
    trap 'rm -f "$PID_FILE"; exit 0' INT TERM EXIT
    pedro_log_ts() { date +%Y-%m-%dT%H:%M:%S.%3N%z; }
    printf '[%s] photos rotator loop started pid=%s interval=%ss\n' "$(pedro_log_ts)" "$$" "$INTERVAL" >> "$LOG_FILE"
    while true; do
      started="$(date +%s.%N)"
      if "$PY_BIN" "$PROBE" 2>&1 | while IFS= read -r line; do
             printf '[%s] %s\n' "$(pedro_log_ts)" "$line"
           done >> "$LOG_FILE"; then
        :
      else
        rc=$?
        printf '[%s] photos rotator: probe failed rc=%s\n' "$(pedro_log_ts)" "$rc" >> "$LOG_FILE"
      fi
      # Compute how long the probe took and sleep the remainder of the
      # interval. Plain `sleep $INTERVAL` drifts because probe + sleep
      # = INTERVAL + drift, and after many cycles the kiosk would see
      # one image per 5.3s instead of one per 5.0s — close enough that
      # you would not notice, but still wrong. Anchor on wall clock.
      now="$(date +%s.%N)"
      elapsed=$(awk -v s="$started" -v n="$now" 'BEGIN{printf "%.3f", n-s}')
      remaining=$(awk -v i="$INTERVAL" -v e="$elapsed" 'BEGIN{v=i-e; if(v<0)v=0; printf "%.3f", v}')
      sleep "$remaining"
    done
    ;;
  *)
    echo "unknown action: $ACTION" >&2
    exit 64
    ;;
esac
