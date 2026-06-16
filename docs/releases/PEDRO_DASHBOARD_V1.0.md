# Pedro Dashboard v1.0

Release timestamp: 2026-06-15T17:48:15Z

## Milestone meaning

Pedro Dashboard v1.0 is the first accepted always-on room dashboard for Kamila.
It is display-first, passive, local, and integration-backed. The UI is frozen as
an accepted baseline; future work should connect or extend behind the JSON state
contracts rather than casually redesigning the screen.

## Accepted v1.0 scope

- Passive kiosk dashboard on the iMac/Pedro display.
- Atomic JSON widget state under `app/state/*.json`.
- No-systemd refresher loop via `scripts/refresh-all-state.sh`.
- Live weather for Warszawa–Służew via Open-Meteo.
- Live cached Google Photos slideshow from the `pedro slideshow` shared album.
- Live Kamila Google Calendar agenda through Pedro-specific OAuth.
- Volleyball VNL 2026 schedule/results kept in `volleyball.json`, separate from Kamila calendar.
- Bottom bar shows time + weekday/date and recent Poland volleyball results.
- Route widget remains gated by its time window and existing source rules.
- OpenViking context contains the project orientation and key connector files.

## Ownership rules

- `calendar.json` is owned by `scripts/refresh-kamila-calendar.py`.
- `volleyball.json` is owned by `scripts/refresh-match-calendar.py`.
- `weather.json` is owned by `scripts/refresh-weather-status.py`.
- `route.json` is owned by `scripts/refresh-route-status.py`.
- `media.json` slideshow is owned by `scripts/refresh-photos-slideshow.py`.
- Mock baseline writer must not overwrite live-owned widgets.

## Kamila calendar rules

- OAuth project is Pedro-specific; do not use Simon/Franchise Google projects.
- Current token has full Google Calendar scope for future STT/TTS write actions.
- Current v1.0 dashboard display path is read-only in behavior.
- Dashboard state exposes only event time, title, and color.
- Do not expose descriptions, guests, locations, links, raw event IDs, or tokens.
- Future writes via STT/TTS require explicit confirmation before create/update/delete.

## Passive UI rules

- The dashboard is an always-on glanceable screen, not an interactive task app.
- Kamila calendar card renders only the visible agenda items.
- Do not show overflow prompts such as `+N more`, `więcej`, or `rozwiń` on the passive screen.
- Avoid clickable/expand affordances unless the display role changes.
- Prefer calm stable state over exposing technical/provider errors.

## Verification snapshot

API snapshot at release:

- calendar: `ok`, source `kamila_google_calendar`, 5 visible events.
- weather: `ok`, city `Warszawa–Służew`.
- media slideshow: `ok`, provider `google_photos_shared_album_cache`.
- volleyball: `ok`, 8 men entries, 8 women entries.
- route: disabled outside active route window.

## Next post-v1 line

Pedro v1.x should focus on reliability and voice foundation:

1. STT/TTS interaction loop.
2. Confirmation-first calendar writes for Kamila.
3. Better failure banners/logging without disturbing the passive screen.
4. Optional calendar display tuning after observing real household use.
