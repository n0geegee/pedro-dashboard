#!/usr/bin/env bash
# Pedro Dashboard — voice daemon status.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

alive="$(pedro_voice_daemon_alive)"
pid=""
if [[ -f "$PEDRO_VOICE_DAEMON_PID_FILE" ]]; then
  pid="$(tr -d '[:space:]' < "$PEDRO_VOICE_DAEMON_PID_FILE" 2>/dev/null || true)"
fi

echo "Pedro voice daemon status"
echo "  pid file        : $PEDRO_VOICE_DAEMON_PID_FILE"
echo "  pid             : ${pid:-<none>}"
echo "  process alive   : $alive"
echo "  log file        : $PEDRO_VOICE_DAEMON_LOG_FILE"
echo "  trigger keycode : ${PEDRO_VOICE_TRIGGER_KEYCODE}"
echo "  mic device      : ${PEDRO_MIC_DEVICE}"
echo "  voice python    : ${PEDRO_VOICE_PY_BIN}"
echo "  display         : ${DISPLAY:-:0}"

if [[ "$alive" != "1" ]] && [[ -f "$PEDRO_VOICE_DAEMON_LOG_FILE" ]]; then
  echo "  log tail:"
  tail -5 "$PEDRO_VOICE_DAEMON_LOG_FILE" 2>/dev/null | sed 's/^/    /'
fi

exit 0
