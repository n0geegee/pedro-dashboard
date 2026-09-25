#!/usr/bin/env bash
# Pedro Dashboard — no-systemd periodic state refresher.
#
# Lifecycle wrapper around scripts/pedro_refresher.py (one long-lived
# scheduler; per-probe cadences and timeouts are defined there).
#
# Usage:
#   scripts/state-refresher.sh --start
#   scripts/state-refresher.sh --stop
#   scripts/state-refresher.sh --status
#   scripts/state-refresher.sh --loop --interval 20   # foreground
#
# --interval is the cadence of the fast local probes (system, hermes, ...);
# network probes (weather, calendar, VNL) run on their own slower cadence.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

PEDRO_STATE_REFRESH_PID_FILE="${PEDRO_STATE_REFRESH_PID_FILE:-$PEDRO_RUN_DIR/state-refresher.pid}"
PEDRO_STATE_REFRESH_LOG_FILE="${PEDRO_STATE_REFRESH_LOG_FILE:-$PEDRO_LOG_DIR/state-refresher.log}"
PEDRO_STATE_REFRESH_STATUS_FILE="${PEDRO_STATE_REFRESH_STATUS_FILE:-$PEDRO_RUN_DIR/state-refresher.status.json}"
PY_BIN="${PEDRO_SERVER_CMD:-python3}"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  PY_BIN=/usr/bin/python3
fi
INTERVAL="${PEDRO_STATE_REFRESH_INTERVAL:-20}"
ACTION="start"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start) ACTION="start"; shift ;;
    --stop) ACTION="stop"; shift ;;
    --status) ACTION="status"; shift ;;
    --loop) ACTION="loop"; shift ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

pedro_ensure_dirs

is_ours() {
  local pid="${1:-}"
  [[ "$pid" =~ ^[0-9]+$ ]] || { echo 0; return 0; }
  if [[ "$(pedro_pid_matches_all "$pid" "pedro_refresher.py")" == "1" ]]; then
    echo 1
  # Pre-scheduler bash loop, so --stop still reaches it after an upgrade.
  elif [[ "$(pedro_pid_matches_all "$pid" "state-refresher.sh" "--loop")" == "1" ]]; then
    echo 1
  else
    echo 0
  fi
}

pid=""
if [[ -f "$PEDRO_STATE_REFRESH_PID_FILE" ]]; then
  pid="$(tr -d '[:space:]' < "$PEDRO_STATE_REFRESH_PID_FILE" 2>/dev/null || true)"
fi

case "$ACTION" in
  status)
    if [[ -n "$pid" ]] && [[ "$(is_ours "$pid")" == "1" ]]; then
      echo "state refresher running: pid=$pid log=$PEDRO_STATE_REFRESH_LOG_FILE"
      if [[ -f "$PEDRO_STATE_REFRESH_STATUS_FILE" ]]; then
        "$PY_BIN" - "$PEDRO_STATE_REFRESH_STATUS_FILE" <<'PY' || true
import json, sys
probes = json.load(open(sys.argv[1]))["probes"]
for name, p in probes.items():
    state = "skipped" if p["skipped"] else ("FAILING x%d" % p["consecutive_failures"] if p["consecutive_failures"] else "ok")
    print("  %-30s every %4ss  last_ok=%s  %s" % (name, int(p["interval_s"]), p["last_ok"] or "-", state))
PY
      fi
      exit 0
    fi
    echo "state refresher not running"
    exit 1
    ;;
  stop)
    if [[ -n "$pid" ]] && [[ "$(is_ours "$pid")" == "1" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 1 25); do
        sleep 0.2
        kill -0 "$pid" 2>/dev/null || break
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PEDRO_STATE_REFRESH_PID_FILE" 2>/dev/null || true
    echo "state refresher stopped"
    exit 0
    ;;
  loop)
    cd "$PEDRO_PROJECT_ROOT" || exit 70
    pedro_load_probe_env
    echo $$ > "$PEDRO_STATE_REFRESH_PID_FILE"
    # exec keeps the pid, so the pid file stays valid for --stop/--status.
    exec "$PY_BIN" "$SCRIPT_DIR/pedro_refresher.py" \
      --base-interval "$INTERVAL" --status-file "$PEDRO_STATE_REFRESH_STATUS_FILE"
    ;;
  start)
    if [[ -n "$pid" ]] && [[ "$(is_ours "$pid")" == "1" ]]; then
      echo "state refresher already running (pid=$pid)"
      exit 0
    fi
    rm -f "$PEDRO_STATE_REFRESH_PID_FILE" 2>/dev/null || true
    : > "$PEDRO_STATE_REFRESH_LOG_FILE"
    setsid "$0" --loop --interval "$INTERVAL" >> "$PEDRO_STATE_REFRESH_LOG_FILE" 2>&1 </dev/null &
    newpid=$!
    echo "$newpid" > "$PEDRO_STATE_REFRESH_PID_FILE"
    sleep 0.5
    if kill -0 "$newpid" 2>/dev/null; then
      echo "state refresher started (pid=$newpid interval=${INTERVAL}s)"
      exit 0
    fi
    echo "ERROR: state refresher exited immediately; see $PEDRO_STATE_REFRESH_LOG_FILE" >&2
    rm -f "$PEDRO_STATE_REFRESH_PID_FILE" 2>/dev/null || true
    exit 74
    ;;
esac
