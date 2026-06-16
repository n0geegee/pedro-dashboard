# Pedro Dashboard — Hermes Oracle Skin v1.2 (2026-06-16)

## Milestone meaning

This release adds the **Hermes Oracle** visual skin to the Pedro Dashboard
on top of the v1.1 layout. The change is **additive and reversible**: it
introduces a new `<body data-skin="oracle">` theme, eight SVG ornaments,
and a small JS helper to inject 4 corner ornaments per panel.

No data, no integration, no layout geometry was changed. v1.1 readability
rules (max 3 calendar events, chronological UL volleyball, Polsat legal
web overlay, 1920x1200 native, no scroll) are preserved.

## Changes

### New files
- `app/static/hermes-oracle.css` — oracle theme layer, ~400 lines, gated
  on `body[data-skin="oracle"]`.
- `app/static/skins/oracle/panel-corner.svg` — single corner ornament,
  used 4× per panel with CSS scale flips.
- `app/static/skins/oracle/header-plate.svg` — title-bar background
  tile.
- `app/static/skins/oracle/ticker-frame.svg` — bottom ticker chassis
  background.
- `app/static/skins/oracle/video-frame.svg` — Polsat video window
  outer border.
- `app/static/skins/oracle/slideshow-frame.svg` — Google Photos frame.
- `app/static/skins/oracle/gem-emerald.svg` — status gem.
- `app/static/skins/oracle/gem-gold.svg` — status gem.
- `app/static/skins/oracle/panel-bg-tile.svg` — subtle obsidian tile.
- `docs/visual/TARGET_RESOLUTION_NOTE.md` — explicit 1920x1200
  resolution pin.
- `docs/visual/current-dashboard-before-hermes-oracle.png` — before
  screenshot (1920x1200).
- `docs/visual/hermes-oracle-after-css-only.png` — oracle CSS, no SVG
  assets.
- `docs/visual/hermes-oracle-after-assets.png` — oracle CSS + SVG
  ornaments.
- `docs/visual/hermes-oracle-final-1920x1200.png` — final state.
- `backups/hermes-oracle-2026-06-16-pre-pedro.tar.gz` — pre-change
  backup of `app/`, `scripts/`, `VERSION`.

### Modified files
- `app/static/index.html` — added
  `<link rel="stylesheet" href="/static/hermes-oracle.css" />`.
- `app/static/app.js`:
  - `ALLOWED_SKINS` now includes `oracle`.
  - `applyUrlSkinOverride()` reads `?skin=oracle` (and persists in
    `localStorage`) for quick previews without changing server state.
  - `applyOracleOrnaments()` injects 4 corner divs per `.card` when
    `body[data-skin="oracle"]`. Idempotent, re-applied on
    `data-skin` mutations via a `MutationObserver`.
- `scripts/set-skin.py` — accepts `oracle` as a manual override.
- `scripts/refresh-season-skin.py` — `oracle` entry in `SKINS`
  dict with label "Hermes Oracle", accent `#43f0b5`.

## How to use

```bash
# Activate oracle skin (manual mode)
cd /home/imac-hermes/projects/pedro_dashboard
python3 scripts/set-skin.py oracle

# Or temporarily without changing server state:
# open http://127.0.0.1:17888/?skin=oracle in the kiosk browser

# Back to seasonal auto
python3 scripts/set-skin.py auto
```

The chosen skin is written to `app/state/skin_override.json` and
reflected in `app/state/skin.json` on the next `refresh-season-skin.py`
cycle (every 30s via the `state-refresher.sh` loop).

## Verification snapshot

- `python3 -m py_compile app/server.py scripts/refresh-season-skin.py
  scripts/set-skin.py` → OK.
- `bash -n` on lifecycle scripts → OK.
- `curl -fsS http://127.0.0.1:17888/api/health` → 200 OK, uptime 15919s.
- All `/static/skins/oracle/*.svg` served HTTP 200.
- 8 panels × 4 corner ornaments injected by `applyOracleOrnaments`.
- All widgets report `status=ok` (route intentionally `disabled`
  outside 06:40–07:40 Europe/Warsaw).
- Screenshots saved at native 1920x1200.

## Honest blockers / TODO

1. **Real GPT-image-2 PNG assets**. Tonight I shipped SVG ornaments
   that match the design spec but are not raster art. When Jurand
   approves the `$imagen` (Hermes OAuth) path, the SVG files in
   `app/static/skins/oracle/` can be replaced 1-for-1 with PNGs
   without changing the CSS hook (file extension only). The CSS
   file extensions will need to be updated from `.svg` to `.png`
   in the `--oracle-*-url` variables.
2. **Codex xhigh review** (DONE 2026-06-16 01:50 UTC). Initial
   findings: 1 P2 + 2 P3. All three fixed:
   - P2: skin override was persisted in `localStorage` (survives
     browser restart, masked `set-skin.py` changes). Moved to
     `sessionStorage`; `?skin=auto|default|clear` now explicitly
     clears the override.
   - P3: `ALLOWED_SKINS` was a plain object; `?skin=constructor`
     passed the check via inherited prototype. Replaced with
     `Object.create(null)` + `Object.hasOwn` check.
   - P3: slideshow background was overridden by the combined
     video+slideshow rule which only set the video frame. Split
     into two separate selectors so both frames apply correctly.
3. **Clawpatch review**. Blocked — project is not a git repo and
   Clawpatch requires `git init` + `clawpatch init`. This was
   already the case before tonight's work and is unchanged.
4. **Kiosk brightness**: not changed (v1.1 schedule still applies).
5. **No regressions** in v1.1 fixtures, route-disabled-out-of-window
   is correct v1.1 behavior, all other widgets report `status=ok`.

## v1.2 rules going forward

- Treat v1.2 as the **accepted Oracle-skin baseline**. v1.1's
  seasonal skins (winter/spring/summer/autumn) remain available and
  the visual style switch is reversible via `set-skin.py auto`.
- Future skin work: prefer extending `hermes-oracle.css` over
  patching `styles.css`. The two layers must stay logically
  separate (theme = variable + override, layout = `styles.css`).
- When a real PNG asset is delivered, drop it into
  `app/static/skins/oracle/` with the same name but `.png`
  extension and update only the CSS variable URL. Do not change
  HTML or JS.
- Do not bundle the dashboard, the kiosk, the photos cache, the
  Polsat profile, or the OAuth tokens into the v1.2 release
  artifact. The release is CSS+JS+SVG only.
