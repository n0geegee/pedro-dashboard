#!/usr/bin/env bash
set -euo pipefail
export DISPLAY="${DISPLAY:-:0}"

# Manual restore for Pedro desktop maintenance.
if ! pgrep -x xfce4-panel >/dev/null 2>&1; then
  nohup xfce4-panel >/tmp/pedro-xfce4-panel-restore.log 2>&1 &
fi
