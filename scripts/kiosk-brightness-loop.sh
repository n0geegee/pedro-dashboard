#!/usr/bin/env bash
set -euo pipefail
cd /home/imac-hermes/projects/pedro_dashboard
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
interval="${PEDRO_BRIGHTNESS_INTERVAL:-300}"
lock="/tmp/pedro-kiosk-brightness-loop.lock"
exec 9>"$lock"
if ! flock -n 9; then
  echo "kiosk brightness loop already running"
  exit 0
fi
mkdir -p app/logs
while true; do
  scripts/set-kiosk-brightness.sh >> app/logs/kiosk-brightness.log 2>&1 || true
  sleep "$interval"
done
