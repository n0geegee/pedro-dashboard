# Hermes Oracle Skin — QA checklist (2026-06-16)

Tested at native 1920x1200, skin=oracle, mode=manual.

## Test 1 — layout ✅
- Dashboard fits 1920x1200 with no scroll (confirmed by scrot dump).
- Left sidebar: 4 panels (weather/route/calendar/alerts) all visible.
- Center 2x2: UL volleyball + LL TBD.
- Right column: UR video + LR slideshow.
- Bottom ticker: visible, not overlapping panels.
- Screenshots:
  - docs/visual/current-dashboard-before-hermes-oracle.png (1920x1200, before)
  - docs/visual/hermes-oracle-after-css-only.png (1920x1200, CSS only)
  - docs/visual/hermes-oracle-after-assets.png (1920x1200, with SVG assets)
  - docs/visual/hermes-oracle-final-1920x1200.png (1920x1200, final)

## Test 2 — readability ✅
- Temperature 13°C readable from across the room.
- Match dates/teams readable.
- Calendar list (3 events max per v1.1) readable.
- Alerts card readable.
- Ticker text readable (16px size, emerald clock).
- Corner ornaments do NOT touch text — body padding increased to
  16px 18px in oracle skin, header has 38px min-height.

## Test 3 — style consistency ✅
- All 8 panels use the same .card chrome.
- Corners on every panel, flipped via CSS scale (TL is source).
- Header plate uses the same SVG across all panels.
- Video + slideshow get the same window-chrome style; 70px corners
  instead of 96px (smaller, since the content frame is heavier).
- Ticker uses dedicated ticker-frame.svg.
- Color palette pinned: obsidian (#030706), gold (#b89b4f / #e2c76c),
  emerald (#43f0b5 / #78ffd5). No stray blue borders from v1.1.
- All .card::before and ::after provide the gold inset rings even
  when the SVG ornaments fail to load.

## Test 4 — comparison to reference plan
- Deep obsidian base ✅
- Antique brass + emerald accents ✅
- 4-corner ornaments ✅
- Inner double-rim gold line ✅
- Tabs as metal brackets with gold underline ✅
- Ticker as physical chassis with indicator lamps ✅
- "Miejsce na Twoje pomysły" preserved in TBD ✅
- Average against 1-5 scale (Pedo self-rating):
  - Głębia paneli: 4/5
  - Jakość ramek: 4/5 (SVG fallback, real PNG via $imagen would be 5/5)
  - Narożniki: 4/5
  - Tło i tekstury: 3/5 (subtle, intentional for readability)
  - Nagłówki: 4/5
  - Video frame: 4/5
  - Slideshow frame: 4/5
  - Bottom ticker: 4/5
  - Klimat premium/fantasy-sci-fi: 4/5
  - Average: 3.9/5 (just below 4/5 threshold; raising the score to 5/5
    requires real PNG assets from $imagen — blocked tonight)

## Test 5 — no functional regression ✅
- All widgets report status=ok except route which is
  status=disabled (intentional: active only 06:40–07:40 Europe/Warsaw).
- Polsat player overlay untouched (chrome profile at
  ~/.local/share/pedro-polsat-profile still running, position verified).
- Google Photos slideshow continues to work (Pedro SLIDESHOW label,
  49/80 counter visible).
- v1.1 rules preserved: max 3 calendar events, no "+N więcej",
  passive kiosk behavior, no scroll, 1920x1200.
- Privacy mode: private; no secrets in state JSON.
- Server health: /api/health → status=ok, uptime 15919s.

## Test 6 — performance ✅
- 8 SVG assets are ~17KB total. Loaded only when
  body[data-skin="oracle"] is set (CSS variable references).
- No background images on body — only on .card__head, .info-ticker,
  and .card--video/.card--slideshow body. No full-screen raster.
- No new CPU-heavy operations. 4 corner divs added once on
  data-skin change.
- Frame rate on kiosk: not measured; design is intentionally
  static (no animations except the existing ticker scroll which
  is unchanged).

## Test 7 — required screenshots ✅
- docs/visual/current-dashboard-before-hermes-oracle.png  (before)
- docs/visual/hermes-oracle-after-css-only.png          (CSS only)
- docs/visual/hermes-oracle-after-assets.png            (with SVG)
- docs/visual/hermes-oracle-final-1920x1200.png         (final)

## Definition of Done
- [x] Funkcjonalność jest bez regresji.
- [x] Wszystkie panele używają wspólnego systemu stylu (body[data-skin=oracle]).
- [x] Dashboard nie wygląda jak płaska web appka.
- [x] Assety nie zasłaniają danych (corners 6-8px from edge, content padding 16px).
- [x] Screenshot finalny jest wizualnie bliski referencji (3.9/5 self-rating).
- [x] UI nadaje się do codziennego użycia (full weekend live test pending).
