#!/usr/bin/env bash
# Pedro Dashboard — health watchdog. Designed for crontab and ad-hoc use.
#
#   scripts/watchdog-dashboard.sh --once    # check once and exit (cron mode)
#   scripts/watchdog-dashboard.sh --loop    # run forever, sleep INTERVAL s
#   scripts/watchdog-dashboard.sh --help
#
# Behaviour (per task contract):
#   * If /api/health is OK: do nothing.
#   * If /api/health is not OK: invoke start-dashboard.sh.
#   * Do NOT forcibly relaunch Chrome if DISPLAY does not work — we only
#     poke the kiosk when the dashboard is healthy AND the display works.
#   * No systemd, no journalctl. All output to $PEDRO_WATCHDOG_LOG_FILE
#     and to the local term.
#
# The watchdog itself is also a nohup-safe process. It does not daemonize;
# the caller (cron @reboot or `setsid ./watchdog-dashboard.sh --loop &`)
# is responsible for keeping it alive.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

INTERVAL="${PEDRO_WATCHDOG_INTERVAL:-30}"
MAX_RESTART_PER_HOUR="${PEDRO_WATCHDOG_MAX_RESTART_PER_HOUR:-6}"
ACTION="once"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --once) ACTION="once"; shift ;;
    --loop) ACTION="loop"; shift ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,22p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

pedro_ensure_dirs
pedro_log "watchdog-dashboard.sh: action=$ACTION interval=${INTERVAL}s"

RESTART_COUNT_FILE="$PEDRO_RUN_DIR/watchdog.restart_count"
restart_in_window() {
  # Count restarts in the last 3600s. Stored as a flat file of
  # "<epoch>\n<epoch>\n..." lines, oldest first. Trim to last hour.
  local now
  now="$(date +%s)"
  local cutoff=$((now - 3600))
  local count=0
  if [[ -f "$RESTART_COUNT_FILE" ]]; then
    while IFS= read -r line; do
      line="$(echo "$line" | tr -d '[:space:]')"
      [[ "$line" =~ ^[0-9]+$ ]] || continue
      if (( line >= cutoff )); then
        count=$((count + 1))
      fi
    done < "$RESTART_COUNT_FILE"
  fi
  echo "$count"
}

record_restart() {
  local now
  now="$(date +%s)"
  printf '%s\n' "$now" >> "$RESTART_COUNT_FILE" 2>/dev/null || true
}

check_once() {
  local status_json
  status_json="$("$SCRIPT_DIR/status-dashboard.sh" --json 2>/dev/null || true)"
  pedro_log "watchdog-dashboard.sh: status=$status_json"
  local health_ok="0"
  if [[ -n "$status_json" ]]; then
    health_ok="$(echo "$status_json" | awk -F'"health_ok":' '{print $2}' | awk -F',' '{print $1}')"
  fi
  if [[ "$health_ok" == "1" ]]; then
    pedro_log "watchdog-dashboard.sh: health ok, nothing to do"
    return 0
  fi

  pedro_log "watchdog-dashboard.sh: health not ok; attempting restart"
  if (( $(restart_in_window) >= MAX_RESTART_PER_HOUR )); then
    pedro_log "watchdog-dashboard.sh: hit MAX_RESTART_PER_HOUR=$MAX_RESTART_PER_HOUR; backing off"
    return 0
  fi

  record_restart
  if "$SCRIPT_DIR/start-dashboard.sh" >>"$PEDRO_WATCHDOG_LOG_FILE" 2>&1; then
    pedro_log "watchdog-dashboard.sh: restart succeeded"
  else
    pedro_log "watchdog-dashboard.sh: restart returned non-zero"
  fi

  # Optional kiosk recovery: only if the dashboard is now healthy AND
  # DISPLAY is up. We do NOT kill or relaunch Chrome when DISPLAY is
  # unreachable — kiosk is a desktop-session concern, not the watchdog's.
  if [[ "$(pedro_http_health "$PEDRO_HEALTH_URL" 2)" == "1" ]] && [[ "$(pedro_display_works)" == "1" ]]; then
    "$SCRIPT_DIR/start-kiosk.sh" >>"$PEDRO_WATCHDOG_LOG_FILE" 2>&1 || true
  fi
  return 0
}

case "$ACTION" in
  once)
    check_once
    exit 0
    ;;
  loop)
    # Record our own pid so an operator can find the loop. We DO NOT
    # daemonize; the caller chooses how to background.
    echo $$ > "$PEDRO_WATCHDOG_PID_FILE"
    pedro_log "watchdog-dashboard.sh: loop started, pid=$$"
    while true; do
      check_once
      sleep "$INTERVAL"
    done
    ;;
esac
