# Pedro Dashboard v1.1

Release timestamp: 2026-06-15T18:35:37Z

## Milestone meaning

Pedro Dashboard v1.1 is the first post-v1 polish milestone after real household feedback from Kamila and Jurand. It keeps the v1.0 passive dashboard baseline and fixes readability/overlay issues discovered during use.

## Changes since v1.0

### Polsat Box Go in UR

- Added legal Polsat Box Go web-player workflow for `Polsat Sport 1`.
- Uses the normal Polsat Box Go page/account in a persistent Chrome profile:
  `~/.local/share/pedro-polsat-profile`.
- No stream extraction, no DRM bypass, no password storage in project files or chat.
- `scripts/refresh-polsat-status.py` writes only UR/player status into `media.json`.
- `scripts/launch-polsat-box-go.sh` launches/repositions the Polsat window in UR.
- Xfwm4 keeps a Chrome titlebar, so the launcher positions the window inside the UR card body instead of covering dashboard headers.

### Kiosk shell / left XFCE panel

- The XFCE side panel was appearing over the dashboard/Polsat overlay.
- Kiosk mode now hides `xfce4-panel` with:
  `scripts/hide-xfce-panel-for-kiosk.sh`.
- XDG autostart installed:
  `~/.config/autostart/pedro-hide-xfce-panel.desktop`.
- Manual restore for desktop maintenance:
  `scripts/show-xfce-panel.sh`.

### Kamila calendar readability

- Calendar card now shows only 3 visible events.
- No `+N more`, `więcej`, `rozwiń`, or overflow prompts on the passive screen.
- Data may still track hidden additional event count internally, but UI stays calm.

### UL volleyball readability

- UL card now renders one global chronological mixed list across women and men.
- It no longer groups all men before women or all women before men.
- Typography, flags, row height, spacing, and metadata were enlarged for room readability.
- Current first six visible matches at release:
  - 17.06 K: Polska — Bułgaria
  - 18.06 K: Polska — Ukraina
  - 20.06 K: Polska — Holandia
  - 21.06 K: Polska — Kanada
  - 24.06 M: Polska — Belgia
  - 25.06 M: Polska — Turcja

## Verification snapshot

- `VERSION`: `1.1`.
- Kamila calendar: 3 visible events, source `kamila_google_calendar`.
- Polsat: provider `polsat_box_go_web`, status `OKNO OTWARTE`.
- UL volleyball: first six matches sorted chronologically across K/M.
- XFCE panel: not running in kiosk mode.

## v1.1 rule going forward

Treat v1.1 as the accepted household readability baseline. Future changes should preserve:

- passive, non-interactive dashboard behavior;
- no left desktop panel overlay;
- Polsat as normal legal web player;
- Kamila calendar max 3 visible items;
- UL volleyball as large, chronological mixed list.
