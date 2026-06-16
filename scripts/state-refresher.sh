#!/usr/bin/env bash
# Pedro Dashboard — no-systemd periodic state refresher.
#
# Usage:
#   scripts/state-refresher.sh --start
#   scripts/state-refresher.sh --stop
#   scripts/state-refresher.sh --status
#   scripts/state-refresher.sh --loop --interval 20
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

PEDRO_STATE_REFRESH_PID_FILE="${PEDRO_STATE_REFRESH_PID_FILE:-$PEDRO_RUN_DIR/state-refresher.pid}"
PEDRO_STATE_REFRESH_LOG_FILE="${PEDRO_STATE_REFRESH_LOG_FILE:-$PEDRO_LOG_DIR/state-refresher.log}"
INTERVAL="${PEDRO_STATE_REFRESH_INTERVAL:-20}"
ACTION="start"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start) ACTION="start"; shift ;;
    --stop) ACTION="stop"; shift ;;
    --status) ACTION="status"; shift ;;
    --loop) ACTION="loop"; shift ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

pedro_ensure_dirs

is_ours() {
  local pid="${1:-}"
  [[ "$pid" =~ ^[0-9]+$ ]] || { echo 0; return 0; }
  [[ "$(pedro_pid_matches_all "$pid" "state-refresher.sh" "--loop")" == "1" ]] && echo 1 || echo 0
}

pid=""
if [[ -f "$PEDRO_STATE_REFRESH_PID_FILE" ]]; then
  pid="$(tr -d '[:space:]' < "$PEDRO_STATE_REFRESH_PID_FILE" 2>/dev/null || true)"
fi

case "$ACTION" in
  status)
    if [[ -n "$pid" ]] && [[ "$(is_ours "$pid")" == "1" ]]; then
      echo "state refresher running: pid=$pid interval=${INTERVAL}s log=$PEDRO_STATE_REFRESH_LOG_FILE"
      exit 0
    fi
    echo "state refresher not running"
    exit 1
    ;;
  stop)
    if [[ -n "$pid" ]] && [[ "$(is_ours "$pid")" == "1" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 1 25); do
        sleep 0.2
        kill -0 "$pid" 2>/dev/null || break
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PEDRO_STATE_REFRESH_PID_FILE" 2>/dev/null || true
    echo "state refresher stopped"
    exit 0
    ;;
  loop)
    echo $$ > "$PEDRO_STATE_REFRESH_PID_FILE"
    printf '[%s] state refresher loop started pid=%s interval=%ss\n' "$(pedro_log_ts)" "$$" "$INTERVAL" >> "$PEDRO_STATE_REFRESH_LOG_FILE"
    while true; do
      if "$SCRIPT_DIR/refresh-all-state.sh" >> "$PEDRO_STATE_REFRESH_LOG_FILE" 2>&1; then
        printf '[%s] refresh ok\n' "$(pedro_log_ts)" >> "$PEDRO_STATE_REFRESH_LOG_FILE"
      else
        rc=$?
        printf '[%s] refresh failed rc=%s\n' "$(pedro_log_ts)" "$rc" >> "$PEDRO_STATE_REFRESH_LOG_FILE"
      fi
      sleep "$INTERVAL"
    done
    ;;
  start)
    if [[ -n "$pid" ]] && [[ "$(is_ours "$pid")" == "1" ]]; then
      echo "state refresher already running (pid=$pid)"
      exit 0
    fi
    rm -f "$PEDRO_STATE_REFRESH_PID_FILE" 2>/dev/null || true
    : > "$PEDRO_STATE_REFRESH_LOG_FILE"
    setsid "$0" --loop --interval "$INTERVAL" >> "$PEDRO_STATE_REFRESH_LOG_FILE" 2>&1 </dev/null &
    newpid=$!
    echo "$newpid" > "$PEDRO_STATE_REFRESH_PID_FILE"
    sleep 0.5
    if kill -0 "$newpid" 2>/dev/null; then
      echo "state refresher started (pid=$newpid interval=${INTERVAL}s)"
      exit 0
    fi
    echo "ERROR: state refresher exited immediately; see $PEDRO_STATE_REFRESH_LOG_FILE" >&2
    rm -f "$PEDRO_STATE_REFRESH_PID_FILE" 2>/dev/null || true
    exit 74
    ;;
esac
