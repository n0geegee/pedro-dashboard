#!/usr/bin/env bash
# Pedro Dashboard — start the v1.4 always-listening "hey pedro" KWS daemon.
#
# Long-lived background process. Vosk streaming STT on the iMac built-in
# mic (plughw:0,2) detects the wake phrase; on detection, 4s of audio is
# captured and run through Gemini STT → allowlist runner → espeak-ng TTS.
# Writes app/state/voice_console.json so the kiosk can show live state.
#
# Replaces v1.3 push-to-talk (which required a keyboard the iMac has not).
#
# Usage:
#   bash scripts/start-voice-kws.sh
#   PEDRO_MIC_DEVICE=plughw:0,0 bash scripts/start-voice-kws.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

pedro_ensure_dirs

if [[ ! -x "$PEDRO_VOICE_PY_BIN" ]]; then
  echo "voice python missing: $PEDRO_VOICE_PY_BIN" >&2
  exit 70
fi
if [[ ! -f "$PEDRO_VOICE_KWS_SCRIPT" ]]; then
  echo "voice kws script missing: $PEDRO_VOICE_KWS_SCRIPT" >&2
  exit 70
fi
if [[ ! -d "$PEDRO_VOSK_MODEL" ]]; then
  echo "vosk model missing: $PEDRO_VOSK_MODEL" >&2
  echo "(download vosk-model-small-pl-0.22 into that path)" >&2
  exit 70
fi
if ! command -v arecord >/dev/null 2>&1; then
  echo "arecord (alsa-utils) is required for KWS capture" >&2
  exit 70
fi
if ! command -v espeak-ng >/dev/null 2>&1; then
  echo "espeak-ng is required for KWS responses" >&2
  exit 70
fi

if [[ "$(pedro_voice_kws_alive)" == "1" ]]; then
  pedro_log "voice kws already running; not starting a second instance"
  echo "voice kws already running"
  exit 0
fi

# Remove stale pid if present
pedro_pid_clean_stale "$PEDRO_VOICE_KWS_PID_FILE"

# Hermes/Pedro env (GOOGLE_API_KEY / GEMINI_API_KEY) must be visible
# to the child so pedro-voice-stt.py can find the Gemini key.
if [[ -f "$PEDRO_HOME/.hermes/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PEDRO_HOME/.hermes/.env"
  set +a
fi

# Launch detached. We do not background it inside a subshell: nohup +
# setsid + redirect so the child outlives our parent shell and the
# terminal. The daemon writes its own pid files (voice_kws.pid and the
# legacy voice_daemon.pid alias).
nohup setsid "$PEDRO_VOICE_PY_BIN" "$PEDRO_VOICE_KWS_SCRIPT" \
  --mic "$PEDRO_MIC_DEVICE" \
  --model "$PEDRO_VOSK_MODEL" \
  --command-seconds "$PEDRO_VOICE_KWS_COMMAND_SECONDS" \
  > "$PEDRO_VOICE_KWS_LOG_FILE" 2>&1 < /dev/null &

# Give it a moment to write the pid file
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if [[ -f "$PEDRO_VOICE_KWS_PID_FILE" ]]; then
    break
  fi
  sleep 0.1
done

if [[ "$(pedro_voice_kws_alive)" == "1" ]]; then
  pedro_log "voice kws started"
  echo "voice kws started"
  exit 0
fi

pedro_log "voice kws failed to start; see $PEDRO_VOICE_KWS_LOG_FILE"
echo "voice kws failed to start; see $PEDRO_VOICE_KWS_LOG_FILE" >&2
exit 1
