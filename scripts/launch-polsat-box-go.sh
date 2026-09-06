#!/usr/bin/env bash
set -euo pipefail

# Pedro Dashboard — launch legal Polsat Box Go web player in the UR area.
# Login is done manually in this persistent Chrome profile; credentials are not
# stored in the Pedro project or passed through chat/CLI.

export DISPLAY="${DISPLAY:-:0}"

# When launched by cron/watchdog/SSH instead of XFCE autostart, DBUS_SESSION_BUS_ADDRESS
# may be missing even though the desktop session has a valid bus. Chrome/DRM/keyring
# can then fail silently or show black video. Reuse the live xfce4-session bus.
if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]] && command -v pgrep >/dev/null 2>&1; then
  xfce_pid="$(pgrep -u "$USER" -x xfce4-session 2>/dev/null | head -1 || true)"
  if [[ -n "${xfce_pid:-}" && -r "/proc/$xfce_pid/environ" ]]; then
    dbus_addr="$(tr '\0' '\n' < "/proc/$xfce_pid/environ" | awk -F= '$1=="DBUS_SESSION_BUS_ADDRESS"{print substr($0, index($0,"=")+1); exit}')"
    if [[ -n "${dbus_addr:-}" ]]; then
      export DBUS_SESSION_BUS_ADDRESS="$dbus_addr"
    fi
  fi
fi
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
#
# Geometry precedence (highest first):
#   1. PEDRO_POLSAT_{X,Y,W,H} exported in the calling environment
#   2. ~/.config/pedro/polsat.env (user-resized geometry persisted by hand)
#   3. OpenViking canonical defaults (PEDRO_DASHBOARD_OV_ORIENTATION_16/Polsat_overlay_st_2more)
PEDRO_POLSAT_ENV="${PEDRO_POLSAT_ENV:-$HOME/.config/pedro/polsat.env}"
if [[ -f "$PEDRO_POLSAT_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$PEDRO_POLSAT_ENV"
fi
X="${PEDRO_POLSAT_X:-1183}"
Y="${PEDRO_POLSAT_Y:-92}"
W="${PEDRO_POLSAT_W:-706}"
H="${PEDRO_POLSAT_H:-488}"

position_polsat_window() {
  if ! command -v xdotool >/dev/null 2>&1; then return 0; fi
  local win=""
  # Match by --user-data-dir (stable for the lifetime of the Chrome process,
  # independent of page title which may be blank until the page loads).
  # Use xdotool --pid matching against the Chrome process that owns our
  # profile, then walk to the visible toplevel window via xdotool search.
  if command -v pgrep >/dev/null 2>&1; then
    local chrome_pid
    chrome_pid="$(pgrep -f "google-chrome.*--user-data-dir=${PROFILE_DIR}" 2>/dev/null | head -1 || true)"
    if [[ -n "$chrome_pid" ]]; then
      for _ in $(seq 1 20); do
        win="$(xdotool search --onlyvisible --pid "$chrome_pid" 2>/dev/null | tail -1 || true)"
        [[ -n "$win" ]] && break
        sleep 0.25
      done
    fi
  fi
  # Fallback to title match if pid-based search did not yield a visible window.
  if [[ -z "$win" ]]; then
    for _ in $(seq 1 20); do
      win="$(xdotool search --onlyvisible --name "Polsat Sport 1" 2>/dev/null | tail -1 || true)"
      [[ -n "$win" ]] && break
      sleep 0.25
    done
  fi
  [[ -z "$win" ]] && return 0
  # Best-effort: Xfwm4 may ignore the no-decoration hint, but keep it set.
  if command -v xprop >/dev/null 2>&1; then
    xprop -id "$win" -f _MOTIF_WM_HINTS 32c -set _MOTIF_WM_HINTS "2, 0, 0, 0, 0" >/dev/null 2>&1 || true
  fi
  # Idempotent ratchet: wait past Xfwm4 splash clamping (which is on
  # for the first ~3s while the window has no decorations and Xfwm4
  # thinks 1164+760=1924 overflows the 1920 screen), then issue
  # windowmove+windowsize repeatedly until xwininfo confirms the
  # OUTER position/size matches env exactly. Capped to 12 attempts
  # over ~12s so cold-boot + slow page load still finish in time.
  for _ in $(seq 1 12); do
    sleep 1
    xdotool windowmove "$win" "$X" "$Y" windowsize "$win" "$W" "$H" windowraise "$win" >/dev/null 2>&1 || true
    sleep 0.3
    local cur_x cur_y cur_w cur_h
    cur_x="$(xdotool getwindowgeometry "$win" 2>/dev/null | awk '/Position:/{print $2}' | tr -d ',')"
    cur_y="$(xdotool getwindowgeometry "$win" 2>/dev/null | awk '/Position:/{print $3}')"
    cur_w="$(xdotool getwindowgeometry "$win" 2>/dev/null | awk '/Geometry:/{print $2}' | cut -dx -f1)"
    cur_h="$(xdotool getwindowgeometry "$win" 2>/dev/null | awk '/Geometry:/{print $2}' | cut -dx -f2)"
    if [[ "$cur_x" == "$X" && "$cur_y" == "$Y" && "$cur_w" == "$W" && "$cur_h" == "$H" ]]; then
      break
    fi
  done
  # Keep the real Polsat Chrome overlay above the fullscreen dashboard.
  if command -v wmctrl >/dev/null 2>&1; then
    wmctrl -i -r "$win" -b add,above >/dev/null 2>&1 || true
  fi
}

# Avoid opening duplicates when the dedicated Chrome profile/window is already alive.
# Use ps filtering for Chrome/Chromium only; plain pgrep -af can falsely match
# the operator shell when this script is launched over SSH.
if ps -eo comm=,args= | awk -v profile="$PROFILE_DIR" -v url="$URL" '
  $1 ~ /^(google-chrome|chrome|chromium|chromium-browser)$/ &&
  (index($0, profile) || index($0, url)) { found=1 }
  END { exit found ? 0 : 1 }
'; then
  position_polsat_window
  echo "Polsat Box Go window/profile already running; positioned in UR"
  exit 0
fi

nohup "$CHROME" \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  --disable-session-crashed-bubble \
  --autoplay-policy=no-user-gesture-required \
  --alsa-output-device=plughw:0,0 \
  --new-window \
  --window-position="$X,$Y" \
  --window-size="$W,$H" \
  --app="$URL" \
  >"$LOG_DIR/polsat-box-go.log" 2>&1 &

position_polsat_window

echo "Launched Polsat Box Go at $URL using profile $PROFILE_DIR"
