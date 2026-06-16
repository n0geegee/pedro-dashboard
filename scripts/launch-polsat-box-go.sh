#!/usr/bin/env bash
set -euo pipefail

# Pedro Dashboard — launch legal Polsat Box Go web player in the UR area.
# Login is done manually in this persistent Chrome profile; credentials are not
# stored in the Pedro project or passed through chat/CLI.

export DISPLAY="${DISPLAY:-:0}"
URL="${PEDRO_POLSAT_URL:-https://polsatboxgo.pl/kanaly-tv/polsat-sport-1/1456452}"
PROFILE_DIR="${PEDRO_POLSAT_PROFILE:-$HOME/.local/share/pedro-polsat-profile}"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/pedro_dashboard"
mkdir -p "$PROFILE_DIR" "$LOG_DIR"

CHROME="${CHROME:-}"
if [[ -z "$CHROME" ]]; then
  for c in google-chrome chromium chromium-browser; do
    if command -v "$c" >/dev/null 2>&1; then CHROME="$c"; break; fi
  done
fi
if [[ -z "$CHROME" ]]; then
  echo "No Chrome/Chromium browser found" >&2
  exit 69
fi

# Xfwm4 keeps a titlebar on Chrome app windows. Use client coordinates that put
# the outer titlebar below the UR card header instead of covering the dashboard.
X="${PEDRO_POLSAT_X:-1183}"
Y="${PEDRO_POLSAT_Y:-92}"
W="${PEDRO_POLSAT_W:-706}"
H="${PEDRO_POLSAT_H:-488}"

position_polsat_window() {
  if ! command -v xdotool >/dev/null 2>&1; then return 0; fi
  local win=""
  for _ in $(seq 1 20); do
    win="$(xdotool search --onlyvisible --name "Polsat Sport 1" 2>/dev/null | tail -1 || true)"
    [[ -n "$win" ]] && break
    sleep 0.25
  done
  [[ -z "$win" ]] && return 0
  # Best-effort: Xfwm4 may ignore the no-decoration hint, but keep it set.
  if command -v xprop >/dev/null 2>&1; then
    xprop -id "$win" -f _MOTIF_WM_HINTS 32c -set _MOTIF_WM_HINTS "2, 0, 0, 0, 0" >/dev/null 2>&1 || true
  fi
  xdotool windowmove "$win" "$X" "$Y" windowsize "$win" "$W" "$H" windowraise "$win" >/dev/null 2>&1 || true
  # Keep the real Polsat Chrome overlay above the fullscreen dashboard.
  if command -v wmctrl >/dev/null 2>&1; then
    wmctrl -i -r "$win" -b add,above >/dev/null 2>&1 || true
  fi
}

# Avoid opening duplicates when the dedicated profile/window is already alive.
if pgrep -af "pedro-polsat-profile|polsatboxgo.pl" >/dev/null 2>&1; then
  position_polsat_window
  echo "Polsat Box Go window/profile already running; positioned in UR"
  exit 0
fi

nohup "$CHROME" \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --disable-session-crashed-bubble \
  --autoplay-policy=no-user-gesture-required \
  --new-window \
  --window-position="$X,$Y" \
  --window-size="$W,$H" \
  --app="$URL" \
  >"$LOG_DIR/polsat-box-go.log" 2>&1 &

position_polsat_window

echo "Launched Polsat Box Go at $URL using profile $PROFILE_DIR"
