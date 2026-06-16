#!/usr/bin/env bash
set -euo pipefail
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

# Pedro kiosk brightness schedule without ambient sensor.
# Day:   06:00-18:59 Europe/Warsaw => full perceived brightness.
# Night: 19:00-05:59 Europe/Warsaw => accepted dim setting 0.68.
# IMPORTANT: idempotent. Do not reapply XRandR if already at target; repeated
# brightness writes can create visible OSD/flash on the physical iMac.

TZ_NAME="${PEDRO_BRIGHTNESS_TZ:-Europe/Warsaw}"
DAY_START="${PEDRO_BRIGHTNESS_DAY_START:-06:00}"
DAY_END="${PEDRO_BRIGHTNESS_DAY_END:-19:00}"
DAY_XRANDR="${PEDRO_DAY_XRANDR_BRIGHTNESS:-1.0}"
NIGHT_XRANDR="${PEDRO_NIGHT_XRANDR_BRIGHTNESS:-0.68}"
DAY_BACKLIGHT="${PEDRO_DAY_BACKLIGHT:-255}"
NIGHT_BACKLIGHT="${PEDRO_NIGHT_BACKLIGHT:-150}"
BACKLIGHT="/sys/class/backlight/radeon_bl0/brightness"
MAX_FILE="/sys/class/backlight/radeon_bl0/max_brightness"
EPSILON="${PEDRO_BRIGHTNESS_EPSILON:-0.005}"

minutes() {
  local hh="${1%%:*}"
  local mm="${1##*:}"
  echo $((10#$hh * 60 + 10#$mm))
}

float_close() {
  python3 - "$1" "$2" "$EPSILON" <<'PY'
import sys
try:
    a=float(sys.argv[1]); b=float(sys.argv[2]); eps=float(sys.argv[3])
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if abs(a-b) <= eps else 1)
PY
}

current_xrandr() {
  xrandr --verbose 2>/dev/null | awk '/^LVDS connected/{p=1} p && /Brightness:/{print $2; exit}' || true
}

now_hm="$(TZ="$TZ_NAME" date +%H:%M)"
now_min="$(minutes "$now_hm")"
start_min="$(minutes "$DAY_START")"
end_min="$(minutes "$DAY_END")"

if (( now_min >= start_min && now_min < end_min )); then
  target_x="$DAY_XRANDR"
  target_hw="$DAY_BACKLIGHT"
  mode="day"
else
  target_x="$NIGHT_XRANDR"
  target_hw="$NIGHT_BACKLIGHT"
  mode="night"
fi

used_hardware=0
action="unchanged"
if [[ -w "$BACKLIGHT" ]]; then
  max="$(cat "$MAX_FILE" 2>/dev/null || echo 255)"
  current_hw="$(cat "$BACKLIGHT" 2>/dev/null || echo "")"
  if [[ "$target_hw" =~ ^[0-9]+$ ]] && (( target_hw > 0 && target_hw <= max )); then
    if [[ "$current_hw" != "$target_hw" ]]; then
      printf "%s\n" "$target_hw" > "$BACKLIGHT"
      action="hardware_set"
    fi
    used_hardware=1
  fi
fi

if command -v xrandr >/dev/null 2>&1; then
  if [[ "$used_hardware" == "1" ]]; then
    # Hardware controls physical backlight; keep software gamma normal, but only
    # if it drifted away from 1.0.
    target_x="1.0"
  fi
  current_x="$(current_xrandr)"
  if [[ -z "$current_x" ]]; then
    xrandr --output LVDS --brightness "$target_x" >/dev/null 2>&1 || true
    action="xrandr_set_no_read"
  elif ! float_close "$current_x" "$target_x"; then
    xrandr --output LVDS --brightness "$target_x" >/dev/null 2>&1 || true
    action="xrandr_set"
  fi
else
  current_x="no_xrandr"
fi

final_x="$(current_xrandr)"
[[ -n "$final_x" ]] || final_x="$current_x"
echo "mode=$mode time=$now_hm target=$target_x current_before=${current_x:-unknown} current_after=${final_x:-unknown} action=$action hardware_target=$target_hw used_hardware=$used_hardware"
