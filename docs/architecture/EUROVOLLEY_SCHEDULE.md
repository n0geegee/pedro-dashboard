# EuroVolley 2026 schedule modules

The dashboard exposes two explicit `SlotRuntime` modules:

- `poland-euro-schedule` → `UL`: Poland’s official CEV 2026 matches for both
  women (`K`) and men (`M`), including the full five-match pool schedule from
  the official calendars plus concrete final-phase matches as CEV publishes
  them. The module renders only rows with a valid timezone-aware `start_at`
  that are currently `live` or are scheduled for the future; past, finished,
  missing, postponed, and malformed rows are excluded. Each row shows the
  Warsaw date and local time.
- `euro-daily-schedule` → `LL`: all concrete matches currently published by
  the official CEV final-phase pages, grouped by Europe/Warsaw date, but only
  while they are `live` or scheduled for the future. Finished and invalid rows
  are omitted. The selected date is the machine’s current Warsaw date; the
  returned CEV feed may also contain the next published days. Each date group
  has an explicit full-width schedule table.

## Sources

- Women final phase: <https://www-old.cev.eu/Competition-Area/competition.aspx?ID=1573&PID=2992>
- Men final phase: <https://www-old.cev.eu/Competition-Area/competition.aspx?ID=1572&PID=2990>
- Women official calendar: <https://webmedia.cev.eu/media/ajxbenea/match-calendars-ev26w.pdf>
- Men official calendar: <https://webmedia.cev.eu/media/slmjk2cz/match-calendars-ev26m.pdf>
- CEV schedule announcement: <https://www.cev.eu/articles/volleyball/cev-eurovolley-2026-full-competition-schedule-now-released/>

The probe never synthesizes knockout opponents. CEV `TBD`, winner, and loser
placeholders are omitted until both teams are concrete on the official page.
When a concrete knockout card has empty date/time fields on the list page, the
probe follows that card's official CEV `MatchPage` link and reads its published
date/time. It still skips the row if the official detail page is unavailable;
no opponent or time is guessed.

## Normalized widget contract

`/api/state.widgets.eurovolley` is a normal state envelope. Its `data` payload
contains:

- `kind: "eurovolley_schedule"`, `edition: 2026`, `timezone:
  "Europe/Warsaw"`;
- `competitions[]` with both `gender: "K"` and `gender: "M"` competitions;
- `matches[]` and `days[]` for concrete CEV current/future published matches;
- `poland_matches[]` for Poland’s K/M pool calendar and concrete final-phase
  matches;
- normalized `home`/`away` teams, `phase`, `source_date`, `source_time`,
  Warsaw `warsaw_date`/`warsaw_time`, UTC `start_at`, `status`, and
  `official_code` where CEV provides one;
- `official_sources[]` and `freshness` metadata.

Venue-local times are converted with the venue’s IANA timezone before grouping
and rendering in Warsaw time. A failed CEV fetch keeps the last good data and
marks the widget `stale`; it does not blank sibling slots.

`refresh-eurovolley.py` is called by the normal 20-second state refresher.
It throttles official CEV fetches to 120 seconds by default
(`EUROVOLLEY_SOURCE_CACHE_SECONDS`) so the ticker and UL/LL remain passive,
live views of the same changing state without hammering the source.

## Poland match-day skin

The server-side `data-pl-matchday` flag is intentionally independent of the
competition. It scans every registered state feed for normalized `home`/`away`
match records, recognizes Poland by flag/code/name, and converts the trusted
timestamp to `Europe/Warsaw`. Competition name, gender, phase, and status are
not filters, so a women's or men's EuroVolley match, a VNL match, or a friendly
activates the same skin. Missing, malformed, and non-Poland records are
ignored; a match that already finished still activates the flag for the rest
of its Warsaw calendar day.
