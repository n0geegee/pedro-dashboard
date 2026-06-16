#!/usr/bin/env bash
# Pedro Dashboard — stop the server started by start-dashboard.sh.
#
# Sends SIGTERM, waits up to 5s, then SIGKILL. Idempotent: if the server
# is not running, exits 0.
#
# Usage:
#   scripts/stop-dashboard.sh
#   scripts/stop-dashboard.sh --quiet
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

QUIET=0
case "${1:-}" in
  --quiet|-q) QUIET=1 ;;
  --help|-h)
    sed -n '2,12p' "$0"
    exit 0
    ;;
  "") : ;;
  *) echo "unknown arg: $1" >&2; exit 64 ;;
esac

pedro_ensure_dirs
pedro_log "stop-dashboard.sh: invoked"

pid=""
if [[ -f "$PEDRO_PID_FILE" ]]; then
  pid="$(tr -d '[:space:]' < "$PEDRO_PID_FILE" 2>/dev/null || true)"
fi

if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]]; then
  [[ "$QUIET" == "0" ]] && echo "dashboard not running (no pid file)"
  pedro_pid_clean_stale "$PEDRO_PID_FILE"
  exit 0
fi

if ! kill -0 "$pid" 2>/dev/null; then
  [[ "$QUIET" == "0" ]] && echo "dashboard not running (stale pid=$pid)"
  pedro_pid_clean_stale "$PEDRO_PID_FILE"
  exit 0
fi
if [[ "$(pedro_pid_matches_all "$pid" "$PEDRO_PROJECT_ROOT/app/server.py")" != "1" ]]; then
  [[ "$QUIET" == "0" ]] && echo "refusing to stop pid=$pid: not a Pedro Dashboard server"
  pedro_log "stop-dashboard.sh: refused non-dashboard pid=$pid cmd=$(pedro_pid_cmdline "$pid")"
  rm -f "$PEDRO_PID_FILE" 2>/dev/null || true
  exit 1
fi

[[ "$QUIET" == "0" ]] && echo "stopping dashboard (pid=$pid)"
kill -TERM "$pid" 2>/dev/null || true
pedro_log "stop-dashboard.sh: SIGTERM -> $pid"

# Wait up to 5s.
for _ in $(seq 1 25); do
  sleep 0.2
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PEDRO_PID_FILE" 2>/dev/null || true
    [[ "$QUIET" == "0" ]] && echo "dashboard stopped (pid=$pid)"
    pedro_log "stop-dashboard.sh: stopped pid=$pid"
    exit 0
  fi
done

# Force-kill.
[[ "$QUIET" == "0" ]] && echo "dashboard did not exit; SIGKILL -> $pid"
kill -KILL "$pid" 2>/dev/null || true
pedro_log "stop-dashboard.sh: SIGKILL -> $pid"

# One final check.
sleep 0.2
if ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PEDRO_PID_FILE" 2>/dev/null || true
  exit 0
fi

echo "ERROR: dashboard process pid=$pid survived SIGKILL" >&2
pedro_log "stop-dashboard.sh: pid=$pid survived SIGKILL"
exit 1
