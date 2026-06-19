# Pedro Dashboard v1.4.1 — volleyball UX polish

Released: 2026-06-19 by Pedro (iMac-Hermes) in response to Jurand's second-pass UX feedback.

## What changed

### `app/static/app.js` — volleyball renderers

**UL widget (`MECZE REPREZENTACJI`):** removed the secondary "X:Y lokalnie" line that
used to render alongside the Warsaw time when a match's source timezone was not
Europe/Warsaw (e.g. Bangkok VNL). The widget now shows ONLY local time:
`12:00 PL · K`. Source timezone display was deemed noise — Jurand does not
travel to matches. CSS class `.vb__when-src` and its rendering path are removed.

**Bottom ticker (`renderTicker`):** every result and every LIVE match now ends
with a `(K)` or `(M)` suffix so women vs men is distinguishable at-a-glance.
Example: `Polska 3:1 Ukraine (K)`, `LIVE Polska vs Ukraine (M)`. This supersedes
the 2026-06-18 ticker-readability rule that said "no M/K prefix" — Jurand
reversed that preference on 2026-06-19.

Implementation:
- `resultTickerText(m)` and `liveTickerText(m)` read `m._group` and append
  `" (K)"` / `" (M)"` when group is known.
- `renderTicker` now passes `_group` to the match object via `Object.assign`
  before calling those helpers.
- LIVE path uses `Object.assign({}, entry.match, { _group: entry.group })`.
- Results path stores `{ group: "M" | "K", match: m }` and copies `entry.group`
  into the synthetic trimmed match.
- `formatTimeSource` (helper around line 392) is kept as dead code — it was
  defined but never invoked by the UL row renderer in v1.4 either. Safe to
  leave for a future cleanup pass.

### `app/static/styles.css`

- No CSS class additions or removals were needed for this release. The class
  name `.vb__when-src` referenced in some session notes never existed in
  v1.4 styles.css — it would have been the styling hook for the source-time
  line that v1.4.1 explicitly does not render, so no CSS rule is needed.

### `VERSION`

- Bumped from `1.3` to `1.4.1`. (The previous commit `2c39640 v1.4 volleyball`
  did not bump VERSION; this release corrects that and uses a patch-level bump
  since this is an incremental polish on top of v1.4.)

## What did NOT change

- The earlier v1.4 volleyball data fetcher (`scripts/refresh-vnl-volleyball.py`)
  and the underlying state file `app/state/volleyball.json` — unchanged.
- Oracle skin v1.2 (hermes-oracle.css) — unchanged.
- Slideshow, weather, route, calendar, alerts widgets — unchanged.
- `app/server.py` — unchanged in this commit (the standalone
  `/api/minimax_usage` endpoint from an earlier WIP session stays as-is).

## Rollback

- Tag `v1.4-pre-pedro-WIP` points at commit `2c39640` (v1.4 volleyball baseline
  before this patch + before any earlier uncommitted WIP changes from prior
  sessions). Use that tag to return to the pre-v1.4.1 state.
- The currently-uncommitted diff in the working tree (volleyball time helpers,
  REFRESH_MS=5000, vb__row/when-sub/badge CSS, _load_minimax_usage endpoint,
  several scripts/ helpers) reflects pre-existing WIP from earlier sessions,
  not v1.4.1. v1.4.1 is contained entirely in this commit.

## Verification

- Screenshot 1920x1200 captured post-bounce:
  `/tmp/kiosk-vb-fix.png` — UL widget shows only local time + group letter,
  ticker shows all 6 results with `(K)` / `(M)` suffix.
- `node -c app/static/app.js` returns exit 0 (no syntax errors).
