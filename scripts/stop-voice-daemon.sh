#!/usr/bin/env bash
# Pedro Dashboard — stop the voice daemon.
#
# Sends SIGTERM, waits up to 5 s, then SIGKILL. Idempotent: returns 0
# even if the daemon was not running.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

if [[ "$(pedro_voice_daemon_alive)" != "1" ]]; then
  pedro_pid_clean_stale "$PEDRO_VOICE_DAEMON_PID_FILE"
  echo "voice daemon not running"
  exit 0
fi

pid="$(tr -d '[:space:]' < "$PEDRO_VOICE_DAEMON_PID_FILE" 2>/dev/null || true)"
if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
  rm -f "$PEDRO_VOICE_DAEMON_PID_FILE" 2>/dev/null || true
  echo "voice daemon not running (stale pid removed)"
  exit 0
fi

kill -TERM "$pid" 2>/dev/null || true
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ! kill -0 "$pid" 2>/dev/null; then
    break
  fi
  sleep 0.5
done
if kill -0 "$pid" 2>/dev/null; then
  kill -KILL "$pid" 2>/dev/null || true
fi

rm -f "$PEDRO_VOICE_DAEMON_PID_FILE" 2>/dev/null || true
pedro_log "voice daemon stopped"
echo "voice daemon stopped"
exit 0
