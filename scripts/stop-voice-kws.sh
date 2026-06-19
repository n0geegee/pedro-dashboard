#!/usr/bin/env bash
# Pedro Dashboard — stop the v1.4 always-listening KWS daemon.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

pid=""
if [[ -f "$PEDRO_VOICE_KWS_PID_FILE" ]]; then
  pid="$(tr -d '[:space:]' < "$PEDRO_VOICE_KWS_PID_FILE" 2>/dev/null || true)"
fi

if [[ -z "$pid" ]] || ! [[ "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
  echo "voice kws not running"
  rm -f "$PEDRO_VOICE_KWS_PID_FILE" "$PEDRO_VOICE_DAEMON_PID_FILE" 2>/dev/null || true
  exit 0
fi

kill -TERM "$pid" 2>/dev/null || true
for _ in $(seq 1 25); do
  sleep 0.2
  kill -0 "$pid" 2>/dev/null || break
done
if kill -0 "$pid" 2>/dev/null; then
  kill -KILL "$pid" 2>/dev/null || true
fi

rm -f "$PEDRO_VOICE_KWS_PID_FILE" "$PEDRO_VOICE_DAEMON_PID_FILE" 2>/dev/null || true
echo "voice kws stopped"
exit 0
