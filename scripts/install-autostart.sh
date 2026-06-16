#!/usr/bin/env bash
# Pedro Dashboard — install XDG .desktop autostart entries.
#
# Per the contract:
#   * Always writes the .desktop files into $PEDRO_XDG_AUTOSTART_DIR.
#   * Always shows the proposed crontab BEFORE writing it, and only
#     installs it when the operator passes --apply-cron. The crontab is
#     printed (and optionally installed) using `crontab -l` / `crontab -`.
#   * No systemd, no journalctl. XDG autostart is the primary mechanism
#     and a crontab fallback is offered but never applied without
#     explicit consent.
#
# Usage:
#   scripts/install-autostart.sh               # write .desktop, show crontab
#   scripts/install-autostart.sh --apply-cron  # also install crontab entries
#   scripts/install-autostart.sh --uninstall   # remove .desktop + crontab
#   scripts/install-autostart.sh --print-only  # print everything, change nothing
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lifecycle_common.sh
source "$SCRIPT_DIR/_lifecycle_common.sh"

ACTION="install"
APPLY_CRON=0
PRINT_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply-cron) APPLY_CRON=1; shift ;;
    --uninstall) ACTION="uninstall"; shift ;;
    --print-only) PRINT_ONLY=1; shift ;;
    --help|-h)
      sed -n '2,22p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

pedro_ensure_dirs

SERVER_DESKTOP_CONTENT=$(cat <<EOF
[Desktop Entry]
Type=Application
Name=Pedro Dashboard server
Comment=Pedro Dashboard HTTP server (127.0.0.1:17888)
Exec=$SCRIPT_DIR/start-dashboard.sh
Icon=utilities-system-monitor
Terminal=false
Categories=Network;Monitor;
X-GNOME-Autostart-enabled=true
EOF
)

REFRESHER_DESKTOP_FILE="$PEDRO_XDG_AUTOSTART_DIR/pedro-dashboard-state-refresher.desktop"
REFRESHER_DESKTOP_CONTENT=$(cat <<EOF
[Desktop Entry]
Type=Application
Name=Pedro Dashboard state refresher
Comment=Pedro Dashboard periodic state refresh loop
Exec=$SCRIPT_DIR/state-refresher.sh --start
Icon=utilities-system-monitor
Terminal=false
Categories=Network;Monitor;
X-GNOME-Autostart-enabled=true
EOF
)

KIOSK_DESKTOP_CONTENT=$(cat <<EOF
[Desktop Entry]
Type=Application
Name=Pedro Dashboard kiosk
Comment=Pedro Dashboard Chrome kiosk window
Exec=$SCRIPT_DIR/start-kiosk.sh
Icon=google-chrome
Terminal=false
Categories=Network;Monitor;
X-GNOME-Autostart-enabled=true
EOF
)

# Crontab fallback: @reboot for the server/refresher, */2 minutes for the watchdog.
PROPOSED_CRON=$(cat <<EOF
# Pedro Dashboard — no-systemd fallback. Edit/delete as you like.
@reboot $SCRIPT_DIR/start-dashboard.sh >> $PEDRO_WATCHDOG_LOG_FILE 2>&1
@reboot $SCRIPT_DIR/state-refresher.sh --start >> $PEDRO_WATCHDOG_LOG_FILE 2>&1
*/2 * * * * $SCRIPT_DIR/watchdog-dashboard.sh --once >> $PEDRO_WATCHDOG_LOG_FILE 2>&1
EOF
)

mkdir -p "$PEDRO_XDG_AUTOSTART_DIR" 2>/dev/null || true

if [[ "$ACTION" == "uninstall" ]]; then
  rm -f "$PEDRO_AUTOSTART_SERVER_FILE" "$REFRESHER_DESKTOP_FILE" "$PEDRO_AUTOSTART_KIOSK_FILE" 2>/dev/null || true
  echo "removed: $PEDRO_AUTOSTART_SERVER_FILE"
  echo "removed: $REFRESHER_DESKTOP_FILE"
  echo "removed: $PEDRO_AUTOSTART_KIOSK_FILE"
  if command -v crontab >/dev/null 2>&1; then
    # Filter out our entries, leave the operator's other crontab alone.
    existing="$(crontab -l 2>/dev/null || true)"
    if [[ -n "$existing" ]]; then
      filtered="$(printf '%s\n' "$existing" | grep -v -F "Pedro Dashboard" | grep -v -F "$SCRIPT_DIR/start-dashboard.sh" | grep -v -F "$SCRIPT_DIR/state-refresher.sh" | grep -v -F "$SCRIPT_DIR/watchdog-dashboard.sh" || true)"
      printf '%s\n' "$filtered" | crontab - 2>/dev/null || true
      echo "removed Pedro Dashboard crontab entries (other entries preserved)"
    fi
  fi
  exit 0
fi

# --- install path ---

echo "== Proposed XDG autostart entries =="
echo "--- $PEDRO_AUTOSTART_SERVER_FILE ---"
echo "$SERVER_DESKTOP_CONTENT"
echo
echo "--- $REFRESHER_DESKTOP_FILE ---"
echo "$REFRESHER_DESKTOP_CONTENT"
echo
echo "--- $PEDRO_AUTOSTART_KIOSK_FILE ---"
echo "$KIOSK_DESKTOP_CONTENT"
echo

if [[ "$PRINT_ONLY" == "1" ]]; then
  echo "== Proposed crontab fallback =="
  echo "$PROPOSED_CRON"
  echo "(--print-only set: nothing written)"
  exit 0
fi

# Write the .desktop files.
printf '%s\n' "$SERVER_DESKTOP_CONTENT" > "$PEDRO_AUTOSTART_SERVER_FILE" || {
  echo "ERROR: failed to write $PEDRO_AUTOSTART_SERVER_FILE" >&2
  exit 1
}
printf '%s\n' "$REFRESHER_DESKTOP_CONTENT" > "$REFRESHER_DESKTOP_FILE" || {
  echo "ERROR: failed to write $REFRESHER_DESKTOP_FILE" >&2
  exit 1
}
printf '%s\n' "$KIOSK_DESKTOP_CONTENT" > "$PEDRO_AUTOSTART_KIOSK_FILE" || {
  echo "ERROR: failed to write $PEDRO_AUTOSTART_KIOSK_FILE" >&2
  exit 1
}
chmod 0644 "$PEDRO_AUTOSTART_SERVER_FILE" "$REFRESHER_DESKTOP_FILE" "$PEDRO_AUTOSTART_KIOSK_FILE" 2>/dev/null || true

# Log the install.
{
  echo "---- $(pedro_log_ts) install-autostart ----"
  echo "wrote: $PEDRO_AUTOSTART_SERVER_FILE"
  echo "wrote: $REFRESHER_DESKTOP_FILE"
  echo "wrote: $PEDRO_AUTOSTART_KIOSK_FILE"
} >> "$PEDRO_AUTOSTART_LOG_FILE" 2>/dev/null || true

echo "wrote: $PEDRO_AUTOSTART_SERVER_FILE"
echo "wrote: $REFRESHER_DESKTOP_FILE"
echo "wrote: $PEDRO_AUTOSTART_KIOSK_FILE"

echo
echo "== Proposed crontab fallback (NOT applied) =="
echo "$PROPOSED_CRON"
echo

if [[ "$APPLY_CRON" == "0" ]]; then
  cat <<'HINT'
The .desktop entries are installed. The crontab above is a fallback for
sessions where XDG autostart is unreliable. To install it, re-run with:

    scripts/install-autostart.sh --apply-cron

To remove everything, run:

    scripts/install-autostart.sh --uninstall
HINT
  exit 0
fi

if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab not available; skipping cron install" >&2
  exit 0
fi

existing="$(crontab -l 2>/dev/null || true)"
# De-duplicate our previous block before appending the current proposal.
filtered="$(printf '%s\n' "$existing" | grep -v -F "Pedro Dashboard" | grep -v -F "$SCRIPT_DIR/start-dashboard.sh" | grep -v -F "$SCRIPT_DIR/state-refresher.sh" | grep -v -F "$SCRIPT_DIR/watchdog-dashboard.sh" || true)"
{
  if [[ -n "$filtered" ]]; then
    printf '%s\n' "$filtered"
  fi
  printf '%s\n' "$PROPOSED_CRON"
} | crontab - 2>/dev/null || {
  echo "ERROR: failed to install crontab" >&2
  exit 1
}
echo "installed crontab entries (existing entries preserved)"
