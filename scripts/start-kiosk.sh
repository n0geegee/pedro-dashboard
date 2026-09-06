#!/usr/bin/env bash
# Pedro Dashboard — start a Chrome kiosk window pointing at the dashboard.
#
# Contract (per task instructions):
#   * Never forcibly launch Chrome when DISPLAY does not work. If the X
#     socket is not reachable, exit 0 with a clear note — the operator
#     can run this manually from their desktop session.
#   * Use a dedicated user-data-dir under $PEDRO_CHROME_PROFILE_DIR.
#   * No systemd / journalctl.
#
# Usage:
#   scripts/start-kiosk.sh
#   scripts/start-kiosk.sh --url http://127.0.0.1:17890/
#   scripts/start-kiosk.sh --stop   # stop an existing kiosk
#   scripts/start-kiosk.sh --status # report kiosk state, do not start
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

URL="http://${PEDRO_HOST}:${PEDRO_PORT}/"
CHROME_BIN="${CHROME_BIN:-/usr/bin/google-chrome}"
ACTION="start"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url|-u) URL="$2"; shift 2 ;;
    --chrome) CHROME_BIN="$2"; shift 2 ;;
    --stop) ACTION="stop"; shift ;;
    --status) ACTION="status"; shift ;;
    --help|-h)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

pedro_ensure_dirs
mkdir -p "$PEDRO_CHROME_PROFILE_DIR" 2>/dev/null || true

kiosk_pid=""
if [[ -f "$PEDRO_KIOSK_PID_FILE" ]]; then
  kiosk_pid="$(tr -d '[:space:]' < "$PEDRO_KIOSK_PID_FILE" 2>/dev/null || true)"
fi

case "$ACTION" in
  stop)
    if [[ -n "$kiosk_pid" ]] && [[ "$kiosk_pid" =~ ^[0-9]+$ ]] && kill -0 "$kiosk_pid" 2>/dev/null; then
      if [[ "$(pedro_pid_matches_all "$kiosk_pid" "$PEDRO_CHROME_PROFILE_DIR" "$URL")" != "1" ]]; then
        echo "refusing to stop pid=$kiosk_pid: not this Pedro kiosk"
        pedro_log "start-kiosk.sh: refused non-kiosk pid=$kiosk_pid cmd=$(pedro_pid_cmdline "$kiosk_pid")"
        rm -f "$PEDRO_KIOSK_PID_FILE" 2>/dev/null || true
        exit 1
      fi
      kill -TERM "$kiosk_pid" 2>/dev/null || true
      pedro_log "start-kiosk.sh: SIGTERM -> $kiosk_pid"
      for _ in $(seq 1 25); do
        sleep 0.2
        if ! kill -0 "$kiosk_pid" 2>/dev/null; then break; fi
      done
      if kill -0 "$kiosk_pid" 2>/dev/null; then
        kill -KILL "$kiosk_pid" 2>/dev/null || true
        pedro_log "start-kiosk.sh: SIGKILL -> $kiosk_pid"
      fi
    fi
    rm -f "$PEDRO_KIOSK_PID_FILE" 2>/dev/null || true
    echo "kiosk stopped"
    exit 0
    ;;
  status)
    if [[ -n "$kiosk_pid" ]] && [[ "$kiosk_pid" =~ ^[0-9]+$ ]] && [[ "$(pedro_pid_matches_all "$kiosk_pid" "$PEDRO_CHROME_PROFILE_DIR" "$URL")" == "1" ]]; then
      echo "kiosk running: pid=$kiosk_pid url=$URL chrome=$CHROME_BIN"
      exit 0
    fi
    echo "kiosk not running"
    exit 1
    ;;
esac

# Idempotency: kiosk already up?
if [[ -n "$kiosk_pid" ]] && [[ "$kiosk_pid" =~ ^[0-9]+$ ]] && [[ "$(pedro_pid_matches_all "$kiosk_pid" "$PEDRO_CHROME_PROFILE_DIR" "$URL")" == "1" ]]; then
  echo "kiosk already running (pid=$kiosk_pid)"
  pedro_log "start-kiosk.sh: already running pid=$kiosk_pid"
  exit 0
fi
pedro_pid_clean_stale "$PEDRO_KIOSK_PID_FILE"

# DISPLAY gate. Do NOT forcibly launch Chrome if X is not reachable.
if [[ "$(pedro_display_works)" != "1" ]]; then
  echo "DISPLAY not reachable (current DISPLAY='${DISPLAY:-}'); skipping kiosk launch."
  echo "  hint: run from a desktop session, or set DISPLAY=:0 and ensure X is up."
  pedro_log "start-kiosk.sh: DISPLAY unreachable; skipping (DISPLAY='${DISPLAY:-}')"
  exit 0
fi

# Make sure the dashboard is up before pointing Chrome at it. During XFCE
# autostart, the kiosk entry can race the server entry by a few seconds, so
# wait briefly before giving up. We still do not start the backend here; the
# dashboard autostart/watchdog owns that.
health_wait_seconds="${PEDRO_KIOSK_HEALTH_WAIT_SECONDS:-30}"
health_ok="0"
for _ in $(seq 0 "$health_wait_seconds"); do
  if [[ "$(pedro_http_health "$PEDRO_HEALTH_URL" 1)" == "1" ]]; then
    health_ok="1"
    break
  fi
  # If the health endpoint is up but dashboard.pid is stale (e.g. PID 3623
  # written by an older start-dashboard.sh run that has since been replaced
  # by a fresh server), try to repair the pid file from the listener PID
  # so future status / restart decisions use the real PID. Self-heal.
  pedro_pid_repair_from_port "$PEDRO_PID_FILE" "$PEDRO_HOST" "$PEDRO_PORT" >/dev/null 2>&1 || true
  sleep 1
done
if [[ "$health_ok" != "1" ]]; then
  echo "dashboard health not OK at $PEDRO_HEALTH_URL after ${health_wait_seconds}s; start it with scripts/start-dashboard.sh first"
  pedro_log "start-kiosk.sh: dashboard health not ok after wait=${health_wait_seconds}s; refusing to launch kiosk"
  exit 75
fi

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "chrome not found at $CHROME_BIN; install google-chrome or set CHROME_BIN" >&2
  pedro_log "start-kiosk.sh: chrome not found at $CHROME_BIN"
  exit 73
fi

: > "$PEDRO_KIOSK_LOG_FILE"
: > "$PEDRO_KIOSK_LOG_ERR_FILE"

# Use --no-first-run and a dedicated profile to avoid polluting the user's
# default Chrome state. --kiosk opens full-screen; we do NOT add
# --noerrdialogs / --disable-session-crashed-bubble in this MVP — the
# operator can layer them later if a kiosk session is real.
#
# setsid(2) detaches Chrome from this script's session: the immediate child
# of this shell is the setsid/glibc helper, not the long-lived Chrome
# process. setsid re-parents Chrome to init (PPid=1) and the wrapper
# exits as soon as exec succeeds. So $! points at a process that is gone
# within milliseconds — a `kill -0 $!` after sleep 0.5 is a guaranteed
# false alarm and was the root cause of the 30s kiosk restart loop.
#
setsid "$CHROME_BIN" \
  --kiosk "$URL" \
  --no-first-run \
  --password-store=basic \
  --no-default-browser-check \
  --disable-background-timer-throttling \
  --disable-renderer-backgrounding \
  --disable-backgrounding-occluded-windows \
  --disable-features=CalculateNativeWinOcclusion \
  --disable-gpu \
  --disable-accelerated-2d-canvas \
  --user-data-dir="$PEDRO_CHROME_PROFILE_DIR" \
  >>"$PEDRO_KIOSK_LOG_FILE" 2>>"$PEDRO_KIOSK_LOG_ERR_FILE" </dev/null &

# To find the real Chrome pid we ask pgrep to match on the unique
# --user-data-dir we passed in. We poll for up to ~3s so a slow start
# (e.g. cold caches, ALSA warm-up) does not trigger a duplicate spawn.
# IMPORTANT: when an old Chrome is already running with the same profile
# (SingletonLock held), a fresh setsid+chrome invocation will fail
# silently within ~50ms ("profile already in use") and pgrep -n will
# return the dying process. The singleton_lock check below catches
# that: if the live lock-holder's pid is alive, that IS our kiosk and
# the new spawn was a no-op. Use the live singleton pid.
KIOSK_PID=""
found_pid=""
launch_started="$(date +%s)"

# First: ask the SingletonLock who the canonical Chrome for this profile
# is. If it points at a live pid whose cmdline matches our profile, that
# is the kiosk pid regardless of what our own setsid invocation did.
singleton_lock="$PEDRO_CHROME_PROFILE_DIR/SingletonLock"
singleton_pid=""
singleton_target=""
if [[ -L "$singleton_lock" ]]; then
  singleton_target="$(readlink "$singleton_lock" 2>/dev/null || true)"
  singleton_pid="${singleton_target##*-}"
fi
if [[ -n "$singleton_pid" ]] && [[ "$singleton_pid" =~ ^[0-9]+$ ]] \
   && kill -0 "$singleton_pid" 2>/dev/null \
   && [[ "$(pedro_pid_matches_all "$singleton_pid" "$PEDRO_CHROME_PROFILE_DIR")" == "1" ]]; then
  KIOSK_PID="$singleton_pid"
fi

# If we did not find a live singleton (cold start, brand-new profile),
# poll pgrep for up to ~3s for a Chrome bound to our profile.
if [[ -z "$KIOSK_PID" ]]; then
  for _ in $(seq 1 30); do
    # pgrep -f matches the full command line; -n returns the newest match.
    # Chrome uses --user-data-dir=<our dir> as a stable, unique token.
    found_pid="$(pgrep -f -n -- "--user-data-dir=${PEDRO_CHROME_PROFILE_DIR}\b.*${URL}" 2>/dev/null || true)"
    if [[ -z "$found_pid" ]]; then
      # Fallback: match on user-data-dir only (URL is sometimes argv-reordered
      # by Chrome, e.g. flags injected via --).
      found_pid="$(pgrep -f -n -- "--user-data-dir=${PEDRO_CHROME_PROFILE_DIR}\b" 2>/dev/null || true)"
    fi
    if [[ -n "$found_pid" ]] && [[ "$found_pid" =~ ^[0-9]+$ ]] \
       && [[ "$(pedro_pid_matches_all "$found_pid" "$PEDRO_CHROME_PROFILE_DIR")" == "1" ]]; then
      KIOSK_PID="$found_pid"
      break
    fi
    sleep 0.1
  done
fi

# If the live singleton pid disagrees with the pgrep result, trust the
# singleton — it is the canonical "this profile is held by THIS Chrome".
# The setsid/Chrome invocations we do when an old instance is alive
# always fail to bind the profile and exit; treating them as "kiosk
# started" would write a wrong pid to the file and re-trigger the loop.
if [[ -n "$KIOSK_PID" ]] && kill -0 "$KIOSK_PID" 2>/dev/null \
   && [[ "$(pedro_pid_matches_all "$KIOSK_PID" "$PEDRO_CHROME_PROFILE_DIR")" == "1" ]]; then
  echo "$KIOSK_PID" > "$PEDRO_KIOSK_PID_FILE"
  pedro_log "start-kiosk.sh: kiosk pid=$KIOSK_PID url=$URL (singleton=${singleton_pid:-none} waited=$(($(date +%s) - launch_started))s)"
  echo "kiosk started (pid=$KIOSK_PID url=$URL profile=$PEDRO_CHROME_PROFILE_DIR)"
  exit 0
fi

# We could not positively identify a Chrome process bound to our profile
# after ~3s. Either Chrome crashed very early or the profile dir is
# unwritable. Surface the actual error log so the operator can debug.
echo "ERROR: chrome did not start a profile-bound process within ~3s; see $PEDRO_KIOSK_LOG_ERR_FILE" >&2
pedro_log "start-kiosk.sh: chrome failed to bind profile (pgrep_pid=${found_pid:-none} singleton=${singleton_pid:-none})"
if [[ -s "$PEDRO_KIOSK_LOG_ERR_FILE" ]]; then
  echo "--- last 5 lines of $PEDRO_KIOSK_LOG_ERR_FILE ---" >&2
  tail -n 5 "$PEDRO_KIOSK_LOG_ERR_FILE" >&2 || true
  echo "--- end ---" >&2
fi
rm -f "$PEDRO_KIOSK_PID_FILE" 2>/dev/null || true
exit 74
