# Pedro Dashboard v1.4.6 — PL match-day flag visible (solid body bg)

Released: 2026-06-19 by Pedro (iMac-Hermes).

## What changed

### `app/static/hermes-oracle.css`

Replaces the v1.4.4+v1.4.5 pseudo-element flag with a solid body background
plus semi-transparent card backs. Flag is now a real biało-czerwone tło
visible across the whole viewport (gaps between cards, around the Polsat
overlay, in the bottom ticker strip).

```css
body[data-skin="oracle"][data-pl-matchday="1"] {
  background: linear-gradient(
    to bottom,
    #ffffff 0% 49.7%,
    #1a1a1a 49.7% 50.3%,
    #dc1414 50.3% 100%
  ) !important;
  background-attachment: fixed !important;
}
body[data-skin="oracle"][data-pl-matchday="1"]::before,
body[data-skin="oracle"][data-pl-matchday="1"]::after { display: none !important; }
body[data-skin="oracle"][data-pl-matchday="1"] .card {
  background: rgba(10, 14, 22, 0.55) !important;
  border-color: rgba(255, 255, 255, 0.18) !important;
}
body[data-skin="oracle"][data-pl-matchday="1"] .card--slideshow,
body[data-skin="oracle"][data-pl-matchday="1"] .card--video,
body[data-skin="oracle"][data-pl-matchday="1"] .card--alerts {
  background: rgba(10, 14, 22, 0.65) !important;
}
```

## Why

v1.4.4 painted the flag on `::before/::after` with z-index 0; v1.4.5 lifted
that to z-index 2. Pixel sampling confirmed both worked, but the dashboard
is so dense (no viewport gaps, ticker + Polsat overlay over the bottom and
right edges) that the flag was technically rendered and visually invisible.
User feedback: "WSTAW KURWA FLAGE POD OKNAMI".

This release uses a solid body background (so the flag IS the page) and
makes the cards semi-transparent so they read against it. `background-
attachment: fixed` keeps the divider line at 50% even when the page
scrolls (it doesn't, but defensive).

## What did NOT change

- `app/server.py` — match-day detection unchanged.
- `app/static/index.html` — body placeholder unchanged.
- `app/static/app.js` — no changes.
- Polsat overlay, ticker, photos rotator, all scripts — unchanged.
- Non-match-day appearance — unchanged (selector requires
  `[data-pl-matchday="1"]`).

## Trade-offs

- Cards become semi-transparent (55% alpha) on match day. Text contrast
  is still good (white/emerald text on dark cards with flag tint behind).
- The Polsat player overlay (opaque) covers part of the upper-right flag.
  Acceptable — it's a live player.
- The bottom ticker covers the bottom red strip. Acceptable — ticker is
  small (60px) and the red still shows through the card gaps.

## Verification

```bash
# 1. State without PL match today:
curl -s http://127.0.0.1:17888/ | grep data-pl-matchday    # = "0"
# Oracle skin looks normal.

# 2. State with fake PL match injected into volleyball.json (today UTC
#    21:00 = Warsaw 23:00):
# After hard reload: kiosk shows white top, red bottom, black divider.
# Pixel sample:
#   top-C    (960, 5)   = RGB(237, 237, 237)   # white
#   mid-C    (960, 600) = RGB(10, 10, 10)      # black divider
#   bot-C    (960, 1195) = RGB(14, 3, 3)       # red

# 3. Revert volleyball.json — kiosk returns to normal oracle skin.
```

## Rollback

```bash
git checkout v1.4.5 -- app/static/hermes-oracle.css
```

## Related

- v1.4.4 release note: `docs/releases/PEDRO_DASHBOARD_V1.4.4.md`
- v1.4.5 release note: `docs/releases/PEDRO_DASHBOARD_V1.4.5.md`
- Recovery plan: `~/.hermes/state/pedro-dashboard-recovery-plan.md`
