# Pedro Dashboard v1.4.4 — PL match-day flag (oracle skin, auto-detect)

Released: 2026-06-19 by Codex (on behalf of Jurand / n0geegee).

## What changed

Re-creates the Polish 50/50 match-day flag under the `oracle` skin as a
**fresh, server-gated** implementation. The flag appears ONLY on days when
the volleyball widget has a Poland match (men OR women) whose `start_at`
falls in the current Europe/Warsaw local window (00:00–23:59). On all
other days the dashboard renders exactly as it did in v1.4.3 — no flag.

### `app/server.py`

Added server-side match-day detection and HTML injection:

- New helper `_poland_match_today(now=None)` scans `volleyball.json` →
  `data.men` + `data.women` for any match where `home.flag == "pl"` or
  `away.flag == "pl"` AND whose `start_at` (UTC ISO-8601) lands in today's
  Europe/Warsaw local window. Tolerates missing/malformed state — yields
  `False` (no flag).
- New helper `_render_index_html(raw_html)` substitutes the
  `{{pl_matchday}}` placeholder in the static `index.html` template with
  `"1"` or `"0"`. Falls back to a regex-based injection on the `<body>`
  tag for older templates that lack the placeholder.
- `/` and `/index.html` now route through `_render_index_html`, so the
  attribute is set on every page load. `/api/state` also exposes
  `poland_match_today: bool` at the top level for easy curl verification.
- Imports added: `time as dtime` from `datetime`, `List` from `typing`,
  `zoneinfo.ZoneInfo`. Stdlib only.

### `app/static/index.html`

The `<body>` tag now carries a placeholder attribute:

```html
<body data-pl-matchday="{{pl_matchday}}">
```

The server substitutes `"1"` or `"0"` on every request.

### `app/static/hermes-oracle.css`

Re-introduces the flag rules under a **two-condition gate**
(`body[data-skin="oracle"][data-pl-matchday="1"]`) so the flag is silent
whenever the skin is not `oracle` or today is not a Poland match day:

```css
body[data-skin="oracle"][data-pl-matchday="1"] {
  background: transparent;
  position: relative;
}
body[data-skin="oracle"][data-pl-matchday="1"]::before {
  /* linear-gradient white 0-50%, red 50-100%, fixed, z-index 0 */
}
body[data-skin="oracle"][data-pl-matchday="1"]::after {
  /* 1px black/18% horizontal divider at top:50%, fixed, z-index 0 */
}
body[data-skin="oracle"][data-pl-matchday="1"] .layout,
body[data-skin="oracle"][data-pl-matchday="1"] .ticker {
  position: relative;
  z-index: 1;
}
```

The `.layout`/`.ticker` `z-index: 1` rule is preserved so dashboard content
sits above the flag.

## What did NOT change

- The `oracle` skin's other CSS (card chrome, ornaments, ticker, panels) — unchanged.
- `app/static/app.js` — untouched. The `data-pl-matchday` attribute is a
  sibling attribute to `data-skin` and is not touched by the JS skin swap.
- `volleyball.json` data shape — unchanged.
- Other widget data, privacy modes, voice console, polsat overlay geometry — unchanged.
- All other working-tree diffs (scripts/*) — left untouched by this release.

## Verification

```bash
# Today (2026-06-19): no Poland match in volleyball widget → flag must be OFF
curl -s http://127.0.0.1:17890/api/state | python3 -c \
  "import sys, json; d=json.load(sys.stdin); print(d['poland_match_today'])"
# Expected: False

# <body> in served HTML carries the placeholder substituted with "0"
curl -s http://127.0.0.1:17890/ | grep -oE 'data-pl-matchday="[01]"'
# Expected: data-pl-matchday="0"

# Tomorrow (2026-06-20): Polska vs Netherlands women VNL at 12:00 PL (10:00 UTC)
# Simulate by patching volleyball.json (or waiting until 2026-06-20 local):
curl -s http://127.0.0.1:17890/api/state | python3 -c \
  "import sys, json; d=json.load(sys.stdin); print(d['poland_match_today'])"
# Expected: True
curl -s http://127.0.0.1:17890/ | grep -oE 'data-pl-matchday="[01]"'
# Expected: data-pl-matchday="1"

# Unit-style sanity check on the helper itself
cd /home/imac-hermes/projects/pedro_dashboard
python3 -c "
from datetime import datetime
from zoneinfo import ZoneInfo
import app.server as s
# Tomorrow's Warsaw midnight is +1 day
now = datetime.now(ZoneInfo('Europe/Warsaw'))
print('today PL match:', s._poland_match_today(now))
# Should print False on 2026-06-19, True on 2026-06-20
"

# CSS sanity — confirm the rule is gated correctly
grep -E 'data-pl-matchday="1"\]::before|data-pl-matchday="1"\]::after|data-pl-matchday="1"\] \.layout' \
  app/static/hermes-oracle.css
# Expected: 4 lines starting with the gated selectors
```

## Rollback

```bash
cd /home/imac-hermes/projects/pedro_dashboard
git checkout v1.4.3 -- app/server.py app/static/index.html app/static/hermes-oracle.css
git tag -d v1.4.4
```

After rollback the dashboard serves plain `<body>` and shows no flag (same
visual as v1.4.3).

## Rationale

v1.4.4 fixes the abrupt removal of the match-day flag in the working tree
(`fe092ee` had introduced it; the working tree then removed the CSS but
left no detection logic). The old commit rendered the flag unconditionally
whenever the oracle skin was active. v1.4.4 makes the flag conditional on
real volleyball data and computes the day window against Europe/Warsaw,
so it auto-appears on Polish match days (today 2026-06-19: OFF; tomorrow
2026-06-20: ON for Polska vs Netherlands women VNL) without manual
intervention.

## Related

- Removed-flag context: commit `fe092ee` (match-day flag backup 20260617-090815)
- Skin contract: `app/static/hermes-oracle.css` (header comment)
- Volleyball data shape: `app/state/volleyball.json`
- Owner: Jurand / n0geegee