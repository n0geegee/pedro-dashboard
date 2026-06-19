#!/usr/bin/env bash
# Pedro Dashboard — status of the v1.4 always-listening KWS daemon.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

pid=""
if [[ -f "$PEDRO_VOICE_KWS_PID_FILE" ]]; then
  pid="$(tr -d '[:space:]' < "$PEDRO_VOICE_KWS_PID_FILE" 2>/dev/null || true)"
fi

if [[ -n "$pid" ]] && [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
  echo "voice kws running: pid=$pid model=$PEDRO_VOSK_MODEL mic=$PEDRO_MIC_DEVICE log=$PEDRO_VOICE_KWS_LOG_FILE"
  exit 0
fi
echo "voice kws not running"
exit 1
