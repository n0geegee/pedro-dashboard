#!/usr/bin/env bash
set -euo pipefail
export DISPLAY="${DISPLAY:-:0}"

# Pedro is a passive kiosk. The XFCE side panel appears over Chrome/Polsat
# overlays, so hide it for the display session. It can be restored with
# scripts/show-xfce-panel.sh.

if pgrep -x xfce4-panel >/dev/null 2>&1; then
  pkill -TERM -x xfce4-panel 2>/dev/null || true
  sleep 1
fi
if pgrep -x xfce4-panel >/dev/null 2>&1; then
  pkill -KILL -x xfce4-panel 2>/dev/null || true
fi
