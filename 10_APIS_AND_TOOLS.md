# 10 — APIs, tools and data sources for Pedro Dashboard

## Executive recommendation

Start with a small, reliable source stack:

1. **Google Maps Routes API** — commute / traffic ETA; likely the only paid/quotable API needed early.
2. **Google Calendar API** — today's calendar, privacy-filtered.
3. **Open-Meteo** — weather, no key for basic use.
4. **TheSportsDB free tier** — first structured sports API candidate for Poland volleyball fixtures; verified basic endpoints work.
5. **Official pages as cross-check/manual fallback** — PZPS / Polska Siatkówka, Volleyball World/VNL, CEV/EuroVolley.
6. **Hermes/OpenViking local health** — internal status only, no raw content.
7. **Voice stack later** — prefer cloud STT/TTS on iMac if local CPU/RAM is too weak.

Do not make sports scraping a blocking dependency for MVP. The dashboard should show `source_status=stale/manual_needed` rather than fail.

---

## Core APIs by feature

### 1. Commute / route / traffic

**Primary:** Google Maps Platform — Routes API.

Needed for:
- travel time to work/school/selected place;
- traffic-aware ETA;
- optional route summary.

Config/env:

```env
GOOGLE_MAPS_API_KEY=
COMMUTE_ORIGIN_LAT=
COMMUTE_ORIGIN_LNG=
COMMUTE_DEST_LAT=
COMMUTE_DEST_LNG=
COMMUTE_DEST_LABEL=
```

Notes:
- Needs Google Cloud project + billing/quotas.
- Use strict API key restrictions.
- Cache aggressively; dashboard does not need refresh every minute outside commute windows.
- MVP can degrade to static text or OSRM/OSM route without live traffic if no key.

Fallback:
- OpenStreetMap/Nominatim + OSRM for approximate route/distance, but no Google-quality traffic.

---

### 2. Calendar

**Primary:** Google Calendar API `events.list` with read-only scope.

Needed for:
- today’s events;
- next event;
- optional focus blocks.

Config/env:

```env
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_PRIVACY=summary_only
```

Notes:
- Requires OAuth, not simple API key.
- Backend must privacy-filter before writing dashboard JSON.
- Guest/private modes must hide titles or replace with generic labels.

---

### 3. Weather

**Primary:** Open-Meteo Forecast API.

Needed for:
- current temp/feels-like;
- precipitation/wind;
- short hourly forecast.

Config/env:

```env
WEATHER_PROVIDER=open-meteo
WEATHER_LAT=
WEATHER_LNG=
WEATHER_LOCATION_LABEL=
```

Notes:
- Basic use does not require API key.
- Good MVP source because it is low-friction and cacheable.

---

## Sports fixtures: what to use

Important distinction:

- **PZPN** = Polish football association. Use for football national teams / Łączy Nas Piłka.
- **PZPS** = Polish volleyball association. Use for volleyball national teams.

The project target is **siatkówka reprezentacji Polski**. Do not treat PZPN as the primary source.

Preferred interpretation:

- **PZPS / Polska Siatkówka** = official Polish volleyball context.
- **Volleyball World / VNL** = official international VNL schedule/results context.
- **CEV / EuroVolley** = official European competition context.
- **TheSportsDB** = free structured JSON candidate for automation, with official pages as verification.

### Recommended sports-source strategy

Use a multi-source adapter with confidence levels:

```text
sports_refresh
  -> primary structured API if available
  -> official page cross-check
  -> manual override file
  -> dashboard JSON with source_status and confidence
```

State output should include:

```json
{
  "status": "ok|stale|error|manual_needed",
  "source_status": "verified|single_source|conflict|manual_override",
  "sport": "volleyball|football",
  "team": "Poland",
  "competition": "VNL / EuroVolley / friendly / UEFA / FIFA",
  "matches": [],
  "sources": []
}
```

---

### Volleyball — candidate sources

#### A. TheSportsDB — best first structured candidate

Verified from this environment:

- `searchteams.php?t=Poland%20Volleyball` returns `idTeam=141825` for `Poland Volleyball`.
- Poland Volleyball has leagues including:
  - `idLeague=5083` — FIVB Volleyball Mens Nations League;
  - `idLeague=5613` — Mens European Volleyball Championship;
  - `idLeague=5344` — FIVB Volleyball Mens World Championship;
  - `idLeague=5042` — Olympics Volleyball.
- `eventsnext.php?id=141825` returned a next Poland Volleyball event.
- `eventsnextleague.php?id=5083` returned VNL events.

Example endpoints:

```text
https://www.thesportsdb.com/api/v1/json/123/searchteams.php?t=Poland%20Volleyball
https://www.thesportsdb.com/api/v1/json/123/eventsnext.php?id=141825
https://www.thesportsdb.com/api/v1/json/123/eventslast.php?id=141825
https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id=5083
```

Caveats:
- Free tier has reduced limits and may return fewer events.
- Community/crowd-sourced data can be incomplete or late.
- Use as primary MVP API candidate, not as sole source of truth.

#### B. Official volleyball pages — cross-check/fallback

Use for verification/manual fallback:

- PZPS / Polska Siatkówka official pages;
- Volleyball World / VNL official pages;
- CEV / EuroVolley pages.

Caveats:
- May not expose stable public APIs.
- Scraping terms and page changes are a risk.
- Prefer storing official URLs and using manual override over brittle scraping in MVP.

#### C. WP SportoweFakty / Siatka.org / Polsat Sport — human-readable fallback only

Useful for manual verification and user-facing links.

Caveats:
- WP content has explicit restrictions against automated copying/exploitation.
- Do not build dashboard dependency on scraping WP pages without permission.

#### D. Paid sports-data APIs

Options found in research:
- BetsAPI;
- Broadage volleyball API;
- Highlightly;
- API-Sports-like providers if volleyball coverage is sufficient.

Use only if free/official sources prove stale and sports widget becomes important.

---

### Football — not MVP

Football/PZPN support is not part of the sports MVP. Keep the notes below only as future reference.

### Football — candidate sources

#### A. PZPN / Łączy Nas Piłka

Good official source for Polish football national-team archive and public pages.

Observed:
- Łączy Nas Piłka has a `biblioteka/mecze` page with events/categories.
- Search did not confirm a stable documented public JSON API.

Recommendation:
- Treat PZPN/ŁNP as official cross-check/manual source unless a stable endpoint is discovered and tested.

#### B. TheSportsDB

Can also cover football teams/leagues and next events, but same caveats: free limits + crowd-sourced freshness.

#### C. football-data.org / API-Football / WorldCupAPI

Could be useful for UEFA/FIFA fixtures, but likely need API keys and may focus on competitions rather than Polish federation pages.

---

## Voice / “hej Pedro” stack

MVP does not need always-listening voice.

Because iMac-Hermes is low-RAM/old hardware, assume local STT/TTS may be too heavy. Prefer a cloud audio backend for practical voice UX unless benchmarks prove local is acceptable.

### Phase A — mock only

Tools:
- `scripts/mock-voice-result.py` writes `voice_console.json`.
- No mic, no STT, no wake-word.

### Phase B — manual/push-to-talk

Candidates:
- **Groq Whisper STT**: fast cloud STT, OpenAI-compatible transcription endpoint; use if Jurand means Groq API. Good candidate for Polish commands and avoids iMac CPU load.
- **xAI Grok STT/TTS**: official xAI docs show voice APIs for STT/TTS; use if Jurand means Grok/xAI API rather than Groq. Treat as usage-based and verify actual account access/pricing before implementing.
- **local faster-whisper**: free/offline, but CPU/RAM risk on iMac; benchmark only after dashboard is stable.
- **OpenAI/Mistral STT**: paid cloud alternatives if Groq/xAI is not suitable.

Needed:

```env
STT_PROVIDER=local|groq|xai|openai|mistral
STT_LANGUAGE=pl
```

If using cloud voice, keep it outside MVP and configure later:

```env
VOICE_PROVIDER=groq|xai|local|openai|mistral
GROQ_API_KEY=
XAI_API_KEY=
```

Do not hard-code this into MVP; MVP only writes mock `voice_console.json`.

### Phase C — wake word

Candidates to research later:
- openWakeWord;
- Porcupine/Picovoice;
- custom lightweight wake phrase detection.

Hard requirement:
- benchmark CPU/RAM before leaving it always-on.
- guest/private modes must disable or restrict active listening.

---

## Internal/local tools

### Hermes status

Use process/status/log-tail probes, but display only:
- running/stopped/stale;
- current model/provider if safe;
- last successful gateway heartbeat;
- update available;
- public error class.

Never display raw prompt/session/log lines.

### OpenViking status

Use local health/search-availability checks only:
- server alive;
- index/account visible;
- last successful query timestamp.

Never display raw retrieved private content unless a voice command explicitly asks and privacy mode allows it.

### System status

Use local commands with timeouts:
- `free -h` / `/proc/meminfo`;
- `df -h`;
- uptime;
- process RSS for Chrome/Hermes/OpenViking/dashboard.

---

## API/key priority list

### Needed soon

1. `GOOGLE_MAPS_API_KEY` — for traffic/commute.
2. Google OAuth credentials/token — for Calendar, later Drive/Photos if needed.

### Nice / low-friction

3. Open-Meteo — no key for basic forecast.
4. TheSportsDB free key `123` for exploratory MVP; premium key only if needed.

### Later

5. Groq or xAI/Grok API key if cloud STT/TTS chosen.
6. Wake-word provider key if commercial engine chosen.
7. Paid sports-data API key only if free sports sources are too stale and the sports widget becomes important.

---

## Source confidence policy

For the dashboard, show confidence rather than pretending certainty:

- `verified`: two independent sources agree or official API/source confirmed.
- `single_source`: one structured source only.
- `manual_override`: user-edited override file used.
- `conflict`: sources disagree; show warning.
- `stale`: data older than TTL.

MVP should support `manual_sports_override.json` so Jurand can fix/force a match without waiting for a perfect API.
