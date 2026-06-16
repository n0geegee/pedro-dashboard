# Pedro Dashboard — project orientation for Pedro/OpenViking

This note is the compact map Pedro should retrieve before changing its own dashboard.

Current accepted milestone: `v1.1` on 2026-06-15.
Release notes: `docs/releases/PEDRO_DASHBOARD_V1.0.md` and `docs/releases/PEDRO_DASHBOARD_V1.1.md`.
Treat v1.1 as the accepted household readability/polish baseline; future work should extend connectors/voice flows without casual UI redesign.

## Project root

`/home/imac-hermes/projects/pedro_dashboard`

## Runtime contract

The dashboard is a passive kiosk served locally on `127.0.0.1:17888`.
Frontend reads `/api/state`, which is composed from JSON files in `app/state/*.json`.
Do not redesign the kiosk UI just to connect data. Add or modify small connector scripts under `scripts/` that atomically write state JSON.

## Refresher

`scripts/state-refresher.sh --loop --interval 20` is the no-systemd background loop. It calls `scripts/refresh-all-state.sh`.
`refresh-all-state.sh` sources `~/.hermes/.env` and then runs live probes.

Important race fix: `scripts/write-mock-state.py` must not overwrite live-owned widgets. Live-owned widgets are:

- `weather.json` -> `scripts/refresh-weather-status.py`
- `route.json` -> `scripts/refresh-route-status.py`
- `calendar.json` -> `scripts/refresh-kamila-calendar.py`
- `volleyball.json` -> `scripts/refresh-match-calendar.py`
- `media.json` slideshow -> `scripts/refresh-photos-slideshow.py`

## Current live widgets

### Google Photos slideshow

Source: Jurand's shared Google Photos album `pedro slideshow`.
Connector: `scripts/refresh-photos-slideshow.py`.
Cache: `app/static/cache/photos/`.
Manifest: `app/state/photos_manifest.json`.
Dashboard uses cached local images, not direct Google hits on every browser refresh. Album/cache refresh is throttled to about 30 minutes; slide changes about every 45 seconds.

### Weather

Connector: `scripts/refresh-weather-status.py`.
Provider: Open-Meteo for `Warszawa–Służew`.
If Open-Meteo/DNS temporarily times out, the connector must keep the last good weather payload visible with `status=ok` and `data.refresh_status=cached_after_probe_error`; do not overwrite `weather.json` with a visible error when cached weather exists. This prevents the weather card from disappearing during transient network failures.
Frontend `errorMsg()` in `app/static/app.js` extracts `message_public`/`message`/`code` from structured error objects so the UI never shows `Błąd: [object Object]`.

### Route ETA

Connector: `scripts/refresh-route-status.py`.
Provider: Google Routes API `computeRoutes`, not legacy Distance Matrix.
Route: `Nowoursynowska 171A, Warszawa` -> `Julianowska 14, Piaseczno`.
Active only `06:40–07:40 Europe/Warsaw`, throttled to max one provider call per 5 minutes.
Routes API requires future `departureTime`; use `now + 60s`.

### Kamila calendar

Connector: `scripts/refresh-kamila-calendar.py`.
It writes `app/state/calendar.json` from Kamila's Google Calendar using the Pedro-specific OAuth token at `~/.hermes/pedro_calendar_token.json` and client secret at `~/.hermes/pedro_google_client_secret.json`.
The OAuth project is Pedro-specific (`pedro-499516`), not any Simon/Franchise project.
Current scope is full Google Calendar (`https://www.googleapis.com/auth/calendar`) because future STT/TTS will create/update events after explicit confirmation; the dashboard read path still exposes only time + title + calendar color.
The connector omits descriptions, meeting links, attendees, locations, and raw event IDs from dashboard state. It uses cached last-good data on transient API/network failures.
Passive UI rule: the card renders only 3 visible agenda items and must not show `+N więcej`, `rozwiń`, or similar overflow prompts on the always-on home screen.
The selected/default calendar currently has owner access and `can_write=true`.

### Polsat Box Go / UR

Connector: `scripts/refresh-polsat-status.py` updates `media.json` transmission status only; it does not scrape or extract streams.
Launcher: `scripts/launch-polsat-box-go.sh` opens the normal Polsat Box Go page for `Polsat Sport 1` in a persistent Chrome profile at `~/.local/share/pedro-polsat-profile`.
Use the normal paid/legal Polsat Box Go account. Do not store credentials in the Pedro project or chat. Xfwm4 keeps a Chrome titlebar, so the launcher positions the window inside the UR card body instead of covering dashboard headers.

### Match calendar / volleyball

Connector: `scripts/refresh-match-calendar.py`.
It writes `app/state/volleyball.json` only. It must not overwrite `calendar.json`, which belongs to Kamila's calendar connector.
It replaces old stale mocks with curated source-backed VNL 2026 schedule for Poland women/men, filtered to upcoming matches. Sources reviewed: TVP Sport / Polsat Sport / Interia Sport.
It also writes `data.recent_results.men` and `data.recent_results.women` with the three latest completed Poland matches for each team. The bottom ticker in `app/static/app.js` uses those recent results first; upcoming fixtures are only a fallback.
The bottom clock renders `HH:MM • weekday date`, e.g. `18:27 • pon. 15.06`.
This is intentionally manual/source-backed until a stable official free API/feed is chosen.

Current nearest entries as of 2026-06-15:

- Women: 2026-06-17 12:00 Polska – Bułgaria, VNL 2026, Bangkok
- Women: 2026-06-18 12:00 Polska – Ukraina, VNL 2026, Bangkok
- Women: 2026-06-20 12:00 Polska – Holandia, VNL 2026, Bangkok
- Women: 2026-06-21 12:00 Polska – Kanada, VNL 2026, Bangkok
- Men: 2026-06-24 20:00 Polska – Belgia, VNL 2026, Gliwice

## Verification checklist before reporting dashboard work done

Run from project root:

```bash
python3 -m py_compile scripts/<changed-script>.py
bash -n scripts/refresh-all-state.sh
scripts/refresh-all-state.sh
curl -fsS http://127.0.0.1:17888/api/state >/tmp/pedro_state.json
```

For UI changes, refresh kiosk and inspect a 1920x1200 screenshot:

```bash
DISPLAY=:0 xdotool key F5 || true
sleep 3
DISPLAY=:0 scrot /tmp/pedro_dashboard_check.png
```

Check for stale mock regressions after at least one background refresher cycle.

## Do not leak secrets

Never print `.env`, API keys, OAuth tokens, Google service account private key, or OAuth authorization codes. Report only presence/health/status.

### XFCE kiosk panel

Pedro runs as a passive kiosk. The XFCE left-side panel can appear over Chrome/Polsat overlays, so kiosk mode hides it with `scripts/hide-xfce-panel-for-kiosk.sh` and XDG autostart `~/.config/autostart/pedro-hide-xfce-panel.desktop`.
To restore the desktop panel for maintenance, run `scripts/show-xfce-panel.sh` from the project root.


### UL volleyball display

The UL volleyball card is for passive household readability. Render one global chronological list of the nearest Poland matches across women and men; do not group all men before women or vice versa. Use large row typography, visible flags, and no small-scroll list when there is enough card space.


### Kiosk brightness

Pedro iMac is too bright at max for passive room use. Linux exposes hardware backlight as `/sys/class/backlight/radeon_bl0`, but normal user writes are root-only in the current session. `scripts/set-kiosk-brightness.sh` is installed via XDG autostart `~/.config/autostart/pedro-kiosk-brightness.desktop`; it uses hardware brightness if writable and otherwise applies XRandR brightness `0.68` on `LVDS`. No ambient light sensor is exposed through `/sys/bus/iio` on this Debian/XFCE setup.


Brightness schedule: without ambient sensors, Pedro uses fixed time windows: 06:00-19:00 Europe/Warsaw = XRandR brightness 1.0; 19:00-06:00 = XRandR brightness 0.68. `scripts/kiosk-brightness-loop.py` runs from XDG autostart every 5 minutes and calls `scripts/set-kiosk-brightness.sh`.


### Seasonal skins

Pedro supports seasonal visual skins as a lightweight CSS/theme layer over the accepted v1.1 layout. The backend exposes `skin.json` through `/api/state` and the frontend applies `body[data-skin]`.

Files:
- `scripts/refresh-season-skin.py` writes `app/state/skin.json`.
- `scripts/set-skin.py auto|default|winter|spring|summer|autumn` sets or clears manual override.
- `app/static/styles.css` contains `body[data-skin="..."]` theme variables.
- `app/static/app.js` applies the skin from `/api/state`.

Default mode is `auto`: winter Dec-Feb, spring Mar-May, summer Jun-Aug, autumn Sep-Nov. Manual override persists in `app/state/skin_override.json` until `scripts/set-skin.py auto` is run. Skins must not change layout geometry, card capacity, or passive-screen rules; they only change ambience/colors.


### Fairytale spring overlay direction

Spring should not be limited to flat green CSS. The preferred direction is a fairytale/magical spring overlay: dark graphite-green base, soft mint glow, subtle vines/buds/fireflies near the edges, calm low-contrast center for card readability. Use GPT2/GPT-image export as a local overlay asset behind the fixed v1.1 layout.

Current prototype asset:
- `app/static/skins/spring-fairytale-overlay.svg`

GPT2 prompt draft:
- `docs/spring-fairytale-gpt2-prompt.txt`

CSS mechanism:
- `body::before` renders `--skin-overlay-url` with configurable opacity/blend mode.
- `body[data-skin="spring"]` points to the overlay.

When a GPT2 export is accepted, save it under `app/static/skins/` as PNG/WebP/SVG and update only the spring `--skin-overlay-url`; do not change layout geometry or card content rules.



### Brightness loop idempotency

The brightness scheduler must be idempotent. Repeated XRandR brightness writes can create visible screen brightening/OSD flashes on the physical iMac. `scripts/set-kiosk-brightness.sh` must read the current LVDS brightness and only call `xrandr --brightness` when the value differs from the schedule target.


### Polsat overlay stacking

Do not treat dashboard text `POLSAT BOX GO / OKNO OTWARTE` as visual proof that the real player overlay is visible. The real Polsat player is a separate Chrome app window (`Polsat Sport 1 - Polsatboxgo.pl`) layered over the UR card. `scripts/launch-polsat-box-go.sh` must both position the window and raise it above the fullscreen dashboard: `xdotool ... windowraise` plus `wmctrl -i -r <win> -b add,above`. Screenshot QA must confirm the real player/titlebar/video controls, not just the placeholder/status card.


### Polsat overlay geometry

Accepted Polsat overlay geometry is the UR inner slot, not the whole right-column width. Current launcher defaults: frame/client target `x=1183 y=92 w=706 h=488`. This leaves dashboard margins visible and keeps the real Chrome/Polsat window inside the UR card without bleeding into the right screen edge or the LR slideshow card. If adjusting later, verify with screenshot and `xwininfo -id <Polsat window> -frame`.

## Baseline lock for next MiniMax/oracle fork — 2026-06-16

- Source of truth is local disk/project docs, not GitHub; this project has no GitHub repo.
- Fork from `/home/imac-hermes/projects/pedro_dashboard`.
- Current accepted baseline: `VERSION = 1.1` with `docs/releases/PEDRO_DASHBOARD_V1.1.md`.
- Baseline lock file: `docs/releases/PEDRO_DASHBOARD_BASELINE_LOCK_2026-06-16.md`.
- Backup before MiniMax/oracle work: `/home/imac-hermes/projects/pedro_dashboard_backups/pedro-dashboard-v1.1-current-before-minimax-oracle-20260616-004920.tgz`.
- Do not fork from `/mnt/linus1/hermes/projects/pedro_dashboard`; that is not the current Pedro working baseline.

