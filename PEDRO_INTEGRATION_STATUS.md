# Pedro Dashboard — integration lock after MVP UI

Status: v1.1 milestone accepted on 2026-06-15. v1.1 is the household readability/polish baseline after Kamila/Jurand feedback. Do not redesign layout casually while connecting sources.

Release notes:
- `docs/releases/PEDRO_DASHBOARD_V1.0.md`
- `docs/releases/PEDRO_DASHBOARD_V1.1.md`
Version file: `VERSION`

## Integration rules

- Display is kiosk-only: no buttons, no links, no click handlers, no mouse/keyboard assumptions.
- Data flows through `app/state/*.json`; frontend stays static and passive.
- Every connector writes atomic JSON and degrades to `stale`/`error` instead of blanking the UI.
- No secrets, raw logs, prompts, Discord text, tokens, or private transcript content in dashboard state.
- Core operational state may be live; personal/content integrations require explicit credential/scope decision.

## Connected now / being kept fresh

### Live operational probes

- `system.json` via `scripts/refresh-system-status.py`:
  - RAM/swap/disk/load/uptime
  - display reachability
  - dashboard process boolean
  - browser availability
- `hermes.json` via `scripts/refresh-hermes-status.py`:
  - Hermes gateway watchdog/process public status
  - gateway UI port open boolean
- `openviking.json` via `scripts/refresh-openviking-status.py`:
  - local OpenViking `/health` only
  - healthy/version/auth mode public fields

### Refresher

- `scripts/refresh-all-state.sh` refreshes mock baseline, then overwrites core widgets with live probes.
- `scripts/state-refresher.sh` keeps state fresh every ~20s without systemd.

## Still mock / requires source decision

- `weather.json`: live Open-Meteo for `Warszawa–Służew` via `scripts/refresh-weather-status.py`; transient timeout/DNS failures keep the last good payload visible as cached weather instead of blanking the card. Frontend error rendering handles structured errors without `[object Object]`.
- `route.json`: live Google Routes API (`computeRoutes`) connector installed for `Nowoursynowska 171A, Warszawa` → `Julianowska 14, Piaseczno`; active only `06:40–07:40`, throttled to max one provider call per 5 min. `GOOGLE_MAPS_API_KEY` is configured on Pedro; forced smoke returned a live driving ETA and distance.
- `calendar.json`: live Kamila Google Calendar connector via `scripts/refresh-kamila-calendar.py`, using Pedro-specific OAuth project/token. Dashboard shows only 3 visible items with time + title + color; descriptions, guests, locations, links, and raw event IDs are omitted. Token currently has full Calendar scope for future STT/TTS write actions after confirmation; current display path is read-only.
- `volleyball.json`: source-backed curated VNL 2026 schedule for Poland women/men, filtered to upcoming matches, plus `recent_results` for the last three completed men/women matches used by the bottom ticker. Sources reviewed: TVP Sport / Polsat Sport / Interia Sport / Sport1. Manual connector is intentional until a stable official free feed/API is chosen.
- `media.json` Polsat: legal Polsat Box Go web-player status via `scripts/refresh-polsat-status.py`; `scripts/launch-polsat-box-go.sh` opens Polsat Sport 1 in a persistent Chrome profile. No stream extraction/DRM bypass; login is manual and credentials are not stored in project files.
- `media.json` Google Photos slideshow: live public shared album connector installed for Jurand's `pedro slideshow` album. `scripts/refresh-photos-slideshow.py` refreshes the album URL list/cache at most every 30 min, stores local images under `app/static/cache/photos/`, and the LR slideshow card renders real cached photos with a passive 45s rotation.
- `voice_console.json`: v1.2 contract is live. Driver is push-to-talk: hold Space (keycode 65) → ALSA capture 4 s → Gemini multimodal STT (`gemini-2.5-flash` with `gemini-flash-latest` fallback) → "hey pedro" prefix gate on transcript → static allowlist runner → espeak-ng TTS (Polish). Daemon: `scripts/pedro_voice_daemon.py` (long-lived, polls X11 via `python-xlib`, no `XGrabKey` so kiosk still receives key). Lifecycle: `start-voice-daemon.sh` / `stop-voice-daemon.sh` / `status-voice-daemon.sh`. Watchdog restarts it via `watchdog-dashboard.sh`. Autostart: `pedro-voice-daemon.desktop`. Design doc: `docs/voice_phase_b_design.md`. Voice venv at `~/.local/share/pedro-voice-venv` (python-xlib only — onnxruntime/tflite/openwakeword are intentionally NOT installed because this Core 2 T7700 CPU lacks SSE4.1/AVX and those libs crash with SIGILL).
- `alerts.json`, `current_focus.json`, `decisions.json`: mock/project notes. Next source can be Hermes cron/jobs, PM file, or a curated local feed.

## Recommended connection order

1. Keep state fresh: core probes + state refresher. (No credentials.)
2. Weather live via Open-Meteo. (No credentials, needs city/coords.)
3. Volleyball source: stable manual/official feed first; ticker uses this immediately.
4. Kamila Google Calendar is live for display; future voice/STT/TTS write path needs confirmation flow before creating/updating events. Photos slideshow is already live from the shared `pedro slideshow` album, with cache refresh every 30 min.
5. Route via privacy-safe origin/destination decision.
6. Voice: microphone -> STT -> Hermes runner -> TTS/result panel.
7. Polsat Box Go is connected as normal web player; next improvement is watchdog/positioning polish if Xfwm4 moves the window after login.

## Kiosk desktop shell

- XFCE side panel is hidden for kiosk mode by `scripts/hide-xfce-panel-for-kiosk.sh` and autostart `~/.config/autostart/pedro-hide-xfce-panel.desktop`.
- Restore manually with `scripts/show-xfce-panel.sh` when desktop maintenance is needed.


## UL volleyball readability

- UL card renders a single chronological mixed list across women and men.
- Typography was enlarged for room readability; do not revert to small grouped rows.


## Kiosk brightness

- Brightness autostart: `~/.config/autostart/pedro-kiosk-brightness.desktop`.
- Script: `scripts/set-kiosk-brightness.sh`.
- Current practical setting: XRandR `LVDS --brightness 0.68`; hardware backlight remains root-only unless system permissions are changed.
- No ambient light sensor is exposed to Linux via IIO in the current setup.


Brightness schedule: 06:00-19:00 Europe/Warsaw uses XRandR brightness 1.0; 19:00-06:00 uses 0.68. Loop: `scripts/kiosk-brightness-loop.py`, autostart: `~/.config/autostart/pedro-kiosk-brightness.desktop`.


## Seasonal skins

- Current skin system: `auto`, `default`, `winter`, `spring`, `summer`, `autumn`.
- Current mode after test: `auto` -> `summer`.
- Change manually with `scripts/set-skin.py winter|spring|summer|autumn|default`.
- Return to automatic seasonal mode with `scripts/set-skin.py auto`.
- Skins are CSS ambience only; do not change v1.1 layout/geometry/passive rules.


## Fairytale spring overlay

- Spring direction should be magical/fairytale, not merely green CSS.
- Overlay slot exists via `body::before` and `--skin-overlay-url`.
- Prototype asset: `app/static/skins/spring-fairytale-overlay.svg`.
- GPT2 prompt: `docs/spring-fairytale-gpt2-prompt.txt`.
- Replace prototype with accepted GPT2 export later; preserve v1.1 layout/capacity/readability.



### Brightness loop idempotency

The brightness scheduler must be idempotent. Repeated XRandR brightness writes can create visible screen brightening/OSD flashes on the physical iMac. `scripts/set-kiosk-brightness.sh` must read the current LVDS brightness and only call `xrandr --brightness` when the value differs from the schedule target.


### Polsat overlay stacking

Do not treat dashboard text `POLSAT BOX GO / OKNO OTWARTE` as visual proof that the real player overlay is visible. The real Polsat player is a separate Chrome app window (`Polsat Sport 1 - Polsatboxgo.pl`) layered over the UR card. `scripts/launch-polsat-box-go.sh` must both position the window and raise it above the fullscreen dashboard: `xdotool ... windowraise` plus `wmctrl -i -r <win> -b add,above`. Screenshot QA must confirm the real player/titlebar/video controls, not just the placeholder/status card.


### Polsat overlay geometry

Accepted Polsat overlay geometry is the UR inner slot, not the whole right-column width. Current launcher defaults: frame/client target `x=1183 y=92 w=706 h=488`. This leaves dashboard margins visible and keeps the real Chrome/Polsat window inside the UR card without bleeding into the right screen edge or the LR slideshow card. If adjusting later, verify with screenshot and `xwininfo -id <Polsat window> -frame`.
