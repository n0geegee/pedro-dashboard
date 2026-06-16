#!/usr/bin/env bash
# Pedro Dashboard — start the voice daemon (push-to-talk "hey pedro").
#
# Long-lived background process. Uses python-xlib to poll the X11
# keyboard state at ~20 Hz and reacts to a keypress of the configured
# trigger key (default Space, keycode 65). Captures ALSA audio on
# press, runs Gemini STT + allowlist runner + espeak-ng TTS, then
# returns to listening_for_wake. See docs/voice_phase_b_design.md.
#
# Usage:
#   bash scripts/start-voice-daemon.sh
#   PEDRO_VOICE_TRIGGER_KEYCODE=105 bash scripts/start-voice-daemon.sh  # Right Ctrl
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

pedro_ensure_dirs

# Need the X display to poll keyboard state. The daemon uses XAUTHORITY
# if set, otherwise the user's $HOME/.Xauthority. We do not start X
# from here — X is the kiosk's job, and the watchdog restarts us if X
# comes back. We just no-op if X is not available.
display="${DISPLAY:-:0}"
export DISPLAY="$display"
if [[ -z "${XAUTHORITY:-}" ]] && [[ -f "$PEDRO_HOME/.Xauthority" ]]; then
  export XAUTHORITY="$PEDRO_HOME/.Xauthority"
fi

if [[ ! -x "$PEDRO_VOICE_PY_BIN" ]]; then
  echo "voice python missing: $PEDRO_VOICE_PY_BIN" >&2
  exit 70
fi
if [[ ! -f "$PEDRO_VOICE_DAEMON_SCRIPT" ]]; then
  echo "voice daemon script missing: $PEDRO_VOICE_DAEMON_SCRIPT" >&2
  exit 70
fi

if [[ "$(pedro_voice_daemon_alive)" == "1" ]]; then
  pedro_log "voice daemon already running; not starting a second instance"
  echo "voice daemon already running"
  exit 0
fi

# Remove stale pid if present
pedro_pid_clean_stale "$PEDRO_VOICE_DAEMON_PID_FILE"

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
# terminal. The daemon writes its own pid file.
nohup setsid "$PEDRO_VOICE_PY_BIN" "$PEDRO_VOICE_DAEMON_SCRIPT" \
  --display "$display" \
  --keycode "${PEDRO_VOICE_TRIGGER_KEYCODE}" \
  --device "$PEDRO_MIC_DEVICE" \
  --state "$PEDRO_PROJECT_ROOT/app/state/voice_console.json" \
  > "$PEDRO_VOICE_DAEMON_LOG_FILE" 2>&1 < /dev/null &

# Give it a moment to write the pid file
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if [[ -f "$PEDRO_VOICE_DAEMON_PID_FILE" ]]; then
    break
  fi
  sleep 0.1
done

if [[ "$(pedro_voice_daemon_alive)" == "1" ]]; then
  pedro_log "voice daemon started"
  echo "voice daemon started"
  exit 0
fi

pedro_log "voice daemon failed to start; see $PEDRO_VOICE_DAEMON_LOG_FILE"
echo "voice daemon failed to start; see $PEDRO_VOICE_DAEMON_LOG_FILE" >&2
exit 1
