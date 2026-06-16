# Pedro Dashboard — visual target v1 from Jurand screenshot

Source reference: Jurand screenshot `img_71b1604d43b5.png` shared in Discord on 2026-06-15.

## Non-negotiable visual direction

This is not the generic 2x2 MVP cockpit. Target is a polished dark glass dashboard branded as HERMES by codex, with dense real-world widgets and media panels.

## Canvas

- Native 1920×1200, 16:10.
- Full-screen dark cockpit, no scroll.
- Soft radial/gradient black-blue background.
- Thin rounded cards, translucent glass/charcoal surfaces, subtle borders.
- Compact typography, dashboard-readable from near/medium distance.

## Header

- Top-left: bird/eagle-style mark + `HERMES` + small `by codex`.
- Top-right: small refresh icon, sun/brightness icon, current time.
- Header is minimal, not a large app title bar.

## Layout

Three-zone asymmetric layout, not equal 2×2:

1. Left column, narrow, stacked widgets:
   - Weather for today.
   - Work route/map card.
   - Calendar for today.
   - Hermes alerts/messages.
2. Center column:
   - Top: `UL: MECZE REPREZENTACJI POLSKI W SIATKÓWCE` with tabs Mężczyźni/Kobiety and match list rows with flags.
   - Bottom: `LL: TBD` placeholder card with dashed inner drop zone and “Miejsce na Twoje pomysły”.
3. Right column:
   - Top: `UR: TRANSMISJA POLSAT SPORT` large video card with volleyball player image, live badge, player controls.
   - Bottom: `LR: SLIDE SHOW — GOOGLE PHOTOS` large landscape slideshow card with nav arrows and counter.

## Widget details from screenshot

### Weather
- Title: `1. POGODA NA DZIŚ`.
- Location Kraków.
- Large temperature `18°C`, weather icon, condition text, small metrics and hourly forecast row.

### Route
- Title: `2. TRASA DO PRACY`.
- Time `7:45 – 8:25`, duration `40 min`.
- Dark map thumbnail with route line.

### Calendar
- Title: `3. KALENDARZ – DZIŚ`.
- Date row and list of timed events with colored dots.

### Alerts
- Title: `4. ALERTY I WIADOMOŚCI OD HERMESA`.
- Card list with colored icon circles, e.g. promo/info.
- Bottom link `Zobacz wszystkie`.

### Volleyball matches
- Tabs with active red underline.
- Rows: date/time, teams, flags, competition/location.
- Focus: Poland national volleyball, not football.

### Video panel
- Large photo/video still.
- Polsat Sport live label.
- Bottom control bar: live dot, sound, progress, settings, fullscreen.

### Slideshow
- Large landscape image.
- Left/right navigation circles.
- Counter at bottom center.

## Difference vs current MVP

Current MVP uses generic 2×2 panels: Bieżący fokus / Alerty / Pedro Voice Console / Decyzje. That satisfies the old minimal skeleton but does not match this screenshot. To match this target, rewrite HTML/CSS/JS layout and mock state contracts around the three-zone media dashboard above.
