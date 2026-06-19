# Pedro Dashboard v1.4.7 — VNL match times in correct UTC instant

Released: 2026-06-19 by Pedro (iMac-Hermes).

## What changed

### `scripts/refresh-vnl-volleyball.py` (+61 lines, -15)

Adds `POOL_TZ_OFFSET_HOURS` dict (13 pools: women Pool_1..9 + men M_Pool_1..4)
mapping each VNL 2026 host venue to its UTC offset in June (DST-aware where
applicable). The Wikipedia parser then converts the "17:00" cell (local match
time) into a UTC instant via `datetime.combine(date, time, host_tz).astimezone(UTC)`.

Without this fix, the script treated every pool as Europe/Warsaw time and
produced `start_at` values that were 5-13 hours wrong for non-European
venues (e.g. Bangkok matches labelled as 17:00 UTC were actually 17:00 ICT,
which is 10:00 UTC). Dashboard JS compares `start_at` to `Date.now()` to
render the LIVE badge — a wrong UTC instant means the LIVE badge flickered
on/off at the wrong times.

## Why

Codex audit (delegate_task, 2026-06-19 ~18:50) confirmed this is a
correctness-only fix with **zero runtime risk**:
- Only affects the `start_at` field written to `app/state/volleyball.json`.
- JS already converts UTC `start_at` to local Warsaw time for display via
  `formatTimeWarsaw()`, so existing user-facing behaviour is unchanged
  when Warsaw IS the venue.
- Non-Warsaw venues now show the correct Warsaw time when Poland plays
  abroad (e.g. Polska vs Netherlands in Bangkok 20.06 12:00 PL — was
  showing 17:00 PL before this fix).

## What did NOT change

- No other files touched.
- `app/server.py`, frontend, kiosk, all scripts except this one — unchanged.
- Volleyball widget UI, ticker behaviour, photos, voice — unchanged.

## Verification

```bash
# Run the refresher once
scripts/refresh-vnl-volleyball.py

# Inspect volleyball.json
python3 -c "
import json
d = json.load(open('app/state/volleyball.json'))
for m in d['data']['men'] + d['data']['women']:
    if m.get('home',{}).get('flag') == 'pl':
        print(f'{m[\"home\"][\"name\"]} vs {m[\"away\"][\"name\"]} | {m[\"start_at\"]} | {m[\"location\"]}')"
# Expected: start_at matches Wikipedia's published local time converted to UTC.
```

## Rollback

```bash
git checkout v1.4.6 -- scripts/refresh-vnl-volleyball.py
```

## Related

- v1.4.6 release note: `docs/releases/PEDRO_DASHBOARD_V1.4.6.md`
- Codex audit: see Pedro session log 2026-06-19 18:45-19:10
- Recovery plan: `~/.hermes/state/pedro-dashboard-recovery-plan.md`