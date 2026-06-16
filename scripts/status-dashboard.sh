#!/usr/bin/env bash
# Pedro Dashboard — print status of the server (process, port, health).
#
# No systemd. Plain shell + curl + ss.
#
# Usage:
#   scripts/status-dashboard.sh
#   scripts/status-dashboard.sh --json   # machine-readable single-line JSON
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

MODE="human"
case "${1:-}" in
  --json|-j) MODE="json" ;;
  --help|-h)
    sed -n '2,12p' "$0"
    exit 0
    ;;
  "") : ;;
  *) echo "unknown arg: $1" >&2; exit 64 ;;
esac

pedro_ensure_dirs

pid=""
pid_alive="false"
if [[ -f "$PEDRO_PID_FILE" ]]; then
  pid="$(tr -d '[:space:]' < "$PEDRO_PID_FILE" 2>/dev/null || true)"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    pid_alive="true"
  fi
fi

port_listen="$(pedro_port_listening "$PEDRO_HOST" "$PEDRO_PORT")"
health="$(pedro_http_health "$PEDRO_HEALTH_URL" 2)"

if [[ "$MODE" == "json" ]]; then
  # Build JSON with printf to avoid a python dependency in the hot path.
  pid_json="${pid:-null}"
  printf '{"host":"%s","port":%s,"pid":%s,"pid_alive":%s,"port_listening":%s,"health_ok":%s,"pid_file":"%s","log_file":"%s","log_err_file":"%s"}\n' \
    "$PEDRO_HOST" "$PEDRO_PORT" "$pid_json" "$pid_alive" "$port_listen" "$health" \
    "$PEDRO_PID_FILE" "$PEDRO_LOG_FILE" "$PEDRO_LOG_ERR_FILE"
  # Exit code: 0 healthy, 1 unhealthy, 2 stopped.
  if [[ "$health" == "1" ]]; then exit 0
  elif [[ "$pid_alive" == "true" || "$port_listen" == "1" ]]; then exit 1
  else exit 2
  fi
fi

# Human-readable
cat <<EOF
Pedro Dashboard status
  host            : $PEDRO_HOST
  port            : $PEDRO_PORT
  health url      : $PEDRO_HEALTH_URL
  pid file        : $PEDRO_PID_FILE
  pid             : ${pid:-<none>}
  process alive   : $pid_alive
  port listening  : $port_listen
  /api/health ok  : $health
  log file        : $PEDRO_LOG_FILE
  log err file    : $PEDRO_LOG_ERR_FILE
EOF

if [[ "$health" == "1" ]]; then exit 0
elif [[ "$pid_alive" == "true" || "$port_listen" == "1" ]]; then exit 1
else exit 2
fi
