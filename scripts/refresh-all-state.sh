#!/usr/bin/env bash
# Pedro Dashboard — refresh all state files once.
#
# Thin wrapper around `pedro_refresher.py --once`: writes the mock baseline
# for widgets without a live source, then runs every live probe once (in
# parallel, each with a timeout). The probe list and cadences live in
# scripts/pedro_refresher.py; the long-running loop is state-refresher.sh.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

PY_BIN="${PEDRO_SERVER_CMD:-python3}"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  PY_BIN=/usr/bin/python3
fi

cd "$PEDRO_PROJECT_ROOT" || exit 70
pedro_ensure_dirs
pedro_load_probe_env

exec "$PY_BIN" "$SCRIPT_DIR/pedro_refresher.py" --once \
  --status-file "$PEDRO_RUN_DIR/state-refresher.status.json"
