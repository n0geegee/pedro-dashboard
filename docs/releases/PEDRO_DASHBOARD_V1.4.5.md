# Pedro Dashboard v1.4.5 — PL match-day flag visibility fix

Released: 2026-06-19 by Pedro (iMac-Hermes) after Codex audit.

## What changed

### `app/static/hermes-oracle.css` (4-line CSS-only fix)

Lifts the v1.4.4 PL flag's stacking position from `z-index: 0` to `z-index: 2`
under `body[data-skin="oracle"][data-pl-matchday="1"]::before, ::after`.
Otherwise the v1.4.4 CSS is unchanged.

## Why

Codex audit (delegate_task, 2026-06-19 ~17:35) found the root cause: the
v1.4.4 flag pseudo-elements were correctly painted at `z-index: 0`, but
`styles.css:147` defines `body > * { z-index: 1 }` and `.layout` (the
grid that holds all dashboard cards) has `display: grid; height: 100%`,
filling the entire viewport. So every visible pixel was covered by a
z-index ≥ 1 element. The flag existed, but it was painted **under** the
dashboard.

## Stacking order after v1.4.5

Back to front:
- body bg (dark oracle radial+linear)
- body::before / body::after (z=0, invisible on oracle skin)
- **PL flag ::before / ::after (z=2)** ← new
- .layout / .ticker / .card / .card::before / .card::after / .oracle-corner (z=1, 2, 4)
- .card > * (z=2)
- .card__num / .card__pos / .card__title in video header (z=3)

The flag at z=2 sits **above** `.layout/.ticker` (z=1) but **below**
`.oracle-corner` (z=4) and the video/slideshow card chrome (z=3).
`pointer-events: none` is unchanged on both pseudo-elements, so it
never intercepts clicks.

## What did NOT change

- `app/server.py` — match-day detection unchanged.
- `app/static/index.html` — body placeholder unchanged.
- `app/static/app.js` — no changes.
- All other files — unchanged.
- Non-match-day appearance — unchanged (the selector requires
  `[data-pl-matchday="1"]`, so the oracle skin's normal look is
  preserved on every day when Poland does not play).

## Verification

```bash
# Default state (no PL match today): flag invisible, oracle skin normal
curl -s http://127.0.0.1:17888/ | grep -oE 'data-pl-matchday="[01]"'  # data-pl-matchday="0"
curl -s http://127.0.0.1:17888/api/state | jq .poland_match_today       # false

# With fake PL match injected into volleyball.json (test only):
# data-pl-matchday="1", poland_match_today=true, kiosk screenshot
# shows a subtle white-to-red 50/50 wash behind the cards.
```

## Rollback

```bash
git checkout v1.4.4 -- app/static/hermes-oracle.css
```

The kiosk will return to v1.4.4 behaviour (flag painted but invisible).

## Related

- v1.4.4 release note: `docs/releases/PEDRO_DASHBOARD_V1.4.4.md`
- Codex audit summary: see Pedro session log 2026-06-19 17:30-17:45
- Recovery plan: `~/.hermes/state/pedro-dashboard-recovery-plan.md`
