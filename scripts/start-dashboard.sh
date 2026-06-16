#!/usr/bin/env bash
# Pedro Dashboard — start server in the background, bound to 127.0.0.1:17888.
#
# No systemd, no journalctl. The server runs in its own session, all stdio
# redirected to files under $PEDRO_LOG_DIR, and a pid file is written to
# $PEDRO_RUN_DIR/dashboard.pid. start-dashboard.sh is idempotent: if the
# server is already healthy on $PEDRO_HOST:$PEDRO_PORT, it exits 0 without
# spawning a second process.
#
# Usage:
#   scripts/start-dashboard.sh            # start (idempotent)
#   scripts/start-dashboard.sh --force    # kill any existing process first
#   PEDRO_PORT=17891 scripts/start-dashboard.sh
#
# Environment overrides:
#   PEDRO_HOST, PEDRO_PORT, PEDRO_PROJECT_ROOT, PEDRO_STATE_DIR,
#   PEDRO_LOG_DIR, PEDRO_RUN_DIR, PEDRO_PID_FILE, PEDRO_SERVER_CMD.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

FORCE=0
case "${1:-}" in
  --force|-f) FORCE=1 ;;
  --help|-h)
    sed -n '2,18p' "$0"
    exit 0
    ;;
  "") : ;;
  *) echo "unknown arg: $1" >&2; exit 64 ;;
esac

pedro_ensure_dirs
pedro_log "start-dashboard.sh: FORCE=$FORCE HOST=$PEDRO_HOST PORT=$PEDRO_PORT"

if [[ "$FORCE" == "1" ]]; then
  "$SCRIPT_DIR/stop-dashboard.sh" || true
fi

# Idempotency: if a healthy instance is already running, exit 0.
if [[ "$(pedro_pid_alive "$PEDRO_PID_FILE")" == "1" ]]; then
  if [[ "$(pedro_http_health "$PEDRO_HEALTH_URL" 2)" == "1" ]]; then
    echo "dashboard already running and healthy (pid=$(cat "$PEDRO_PID_FILE"))"
    pedro_log "start-dashboard.sh: already running and healthy"
    exit 0
  fi
  pedro_log "start-dashboard.sh: pid alive but health failed; restarting"
  "$SCRIPT_DIR/stop-dashboard.sh" || true
fi
pedro_pid_clean_stale "$PEDRO_PID_FILE"

# Sanity-check the project root / server module.
if [[ ! -f "$PEDRO_PROJECT_ROOT/app/server.py" ]]; then
  echo "ERROR: cannot find $PEDRO_PROJECT_ROOT/app/server.py" >&2
  pedro_log "start-dashboard.sh: missing app/server.py at $PEDRO_PROJECT_ROOT"
  exit 70
fi

# Pick the python interpreter. Prefer $PEDRO_SERVER_CMD if executable;
# otherwise fall back to /usr/bin/python3.
PY_BIN="$PEDRO_SERVER_CMD"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  if [[ -x /usr/bin/python3 ]]; then
    PY_BIN=/usr/bin/python3
  else
    echo "ERROR: no python3 interpreter available" >&2
    pedro_log "start-dashboard.sh: no python3 interpreter"
    exit 71
  fi
fi

# Truncate old runtime logs for a clean server start; do not keep multi-run concat.
: > "$PEDRO_LOG_FILE"
: > "$PEDRO_LOG_ERR_FILE"

# Refresh baseline state before the browser/server reads it. Keep this non-fatal:
# stale/degraded widgets are better than a failed start. Prefer the all-state
# refresher wrapper so live probes overwrite mock baseline consistently.
if [[ -x "$SCRIPT_DIR/refresh-all-state.sh" ]]; then
  "$SCRIPT_DIR/refresh-all-state.sh" >>"$PEDRO_LOG_FILE" 2>>"$PEDRO_LOG_ERR_FILE" || true
else
  if [[ -f "$SCRIPT_DIR/write-mock-state.py" ]]; then
    "$PY_BIN" "$SCRIPT_DIR/write-mock-state.py" >>"$PEDRO_LOG_FILE" 2>>"$PEDRO_LOG_ERR_FILE" || true
  fi
  for probe in refresh-system-status.py refresh-hermes-status.py refresh-openviking-status.py; do
    if [[ -f "$SCRIPT_DIR/$probe" ]]; then
      "$PY_BIN" "$SCRIPT_DIR/$probe" >>"$PEDRO_LOG_FILE" 2>>"$PEDRO_LOG_ERR_FILE" || true
    fi
  done
fi

# Keep state fresh after startup; idempotent and non-fatal.
if [[ -x "$SCRIPT_DIR/state-refresher.sh" ]]; then
  PEDRO_STATE_REFRESH_INTERVAL="${PEDRO_STATE_REFRESH_INTERVAL:-20}" \
    "$SCRIPT_DIR/state-refresher.sh" --start >>"$PEDRO_LOG_FILE" 2>>"$PEDRO_LOG_ERR_FILE" || true
fi

# Spawn in a new session so the dashboard is decoupled from the calling
# shell. setsid + redirected stdio + pidfile hand-off is the standard
# no-systemd pattern.
DASHBOARD_HOST="$PEDRO_HOST" DASHBOARD_PORT="$PEDRO_PORT" \
  setsid "$PY_BIN" "${PEDRO_SERVER_ARGS_DEFAULT[@]}" \
  >>"$PEDRO_LOG_FILE" 2>>"$PEDRO_LOG_ERR_FILE" </dev/null &

SERVER_PID=$!
echo "$SERVER_PID" > "$PEDRO_PID_FILE"
pedro_log "start-dashboard.sh: spawned pid=$SERVER_PID"

# Wait up to ~6s for the server to come up.
for _ in $(seq 1 30); do
  sleep 0.2
  if [[ "$(pedro_http_health "$PEDRO_HEALTH_URL" 1)" == "1" ]]; then
    echo "dashboard started (pid=$SERVER_PID, http://$PEDRO_HOST:$PEDRO_PORT/)"
    pedro_log "start-dashboard.sh: health ok after spawn"
    exit 0
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "ERROR: server process exited before becoming healthy; see $PEDRO_LOG_ERR_FILE" >&2
    pedro_log "start-dashboard.sh: server process died before health"
    rm -f "$PEDRO_PID_FILE" 2>/dev/null || true
    exit 72
  fi
done

echo "WARN: server spawned (pid=$SERVER_PID) but /api/health not yet OK after 6s; check $PEDRO_LOG_ERR_FILE" >&2
pedro_log "start-dashboard.sh: WARN health not ok after 6s; pid=$SERVER_PID"
exit 72
