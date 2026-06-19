# Pedro Dashboard v1.4.3 — polsat overlay geometry from env file

Released: 2026-06-19 by Pedro (iMac-Hermes).

## What changed

### `scripts/launch-polsat-box-go.sh`

Added support for sourcing a user-overridden Polsat Box Go window geometry
from `~/.config/pedro/polsat.env`. The script now applies the geometry
with this precedence (highest first):

1. `PEDRO_POLSAT_{X,Y,W,H}` exported in the calling environment (e.g. from
   `scripts/watchdog-dashboard.sh` if it ever needs to override).
2. `~/.config/pedro/polsat.env` (user-resized geometry, persists across
   kiosk bounces and Polsat Chrome restarts).
3. OpenViking canonical defaults `x=1183 y=92 w=706 h=488`
   (`PEDRO_DASHBOARD_OV_ORIENTATION_16/Polsat_overlay_st_2more`).

Path of the env file can itself be overridden via `PEDRO_POLSAT_ENV`.

## What did NOT change

- The OV canonical default (`1183 92 706 488`) — unchanged. The env file is
  opt-in; without it the script falls back to OV canonical exactly as before.
- The persistent Chrome profile for Polsat (`~/.local/share/pedro-polsat-profile`)
  — unchanged.
- The duplicate-detection logic — unchanged.
- The `_MOTIF_WM_HINTS` no-decoration hint — unchanged.
- The `wmctrl -b add,above` keep-above-the-kiosk step — unchanged.

## Verification

```bash
# Source env file manually and confirm geometry
bash -c 'source /home/imac-hermes/.config/pedro/polsat.env; \
         echo "X=$PEDRO_POLSAT_X Y=$PEDRO_POLSAT_Y W=$PEDRO_POLSAT_W H=$PEDRO_POLSAT_H"'
# Expected: X=1167 Y=64 W=756 H=565

# Fallback when env file absent
bash -c 'X=${PEDRO_POLSAT_X:-1183}; Y=${PEDRO_POLSAT_Y:-92}; \
         W=${PEDRO_POLSAT_W:-706}; H=${PEDRO_POLSAT_H:-488}; echo "$X $Y $W $H"'
# Expected: 1183 92 706 488

# Script syntax
bash -n scripts/launch-polsat-box-go.sh && echo OK
```

## Rollback

```bash
git checkout v1.4.2 -- scripts/launch-polsat-box-go.sh
rm -f ~/.config/pedro/polsat.env
```

The script will continue to apply OV canonical defaults `1183 92 706 488`
after rollback.

## Rationale

Before v1.4.3, Jurand's hand-tuned geometry (`1167 64 756 565`) was lost
every time the Polsat Chrome overlay was killed/restarted — the launcher
would rebuild the window at OV canonical. v1.4.3 makes the user resize
sticky across restarts without losing the OV canonical as a safe default
for first-time setups.

## Related

- Polsat overlay geometry history: `viking://user/default/memories/events/2026/06/19/polsat_overlay_geometry.md`
- OpenViking canonical geometry: `viking://resources/PEDRO_DASHBOARD_OV_ORIENTATION_16/.../Polsat_overlay_st_2more_c745cef4.md`
