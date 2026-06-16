# 11 — Free-first volleyball + voice guidance

## Cel tej notatki

Ten plik ma zapobiec błądzeniu implementatora/Codexa przy źródłach danych. Pedro Dashboard ma być możliwie darmowy, lekki i dopasowany do iMac-Hermes.

Najważniejsze decyzje:

- Widget sportowy dotyczy **siatkówki reprezentacji Polski**, nie piłki nożnej.
- **PZPS / Polska Siatkówka** jest właściwym polskim kontekstem official dla siatkówki.
- **PZPN** nie jest źródłem dla tego widgetu; PZPN dotyczy piłki nożnej.
- MVP ma używać źródeł darmowych/free-first.
- STT/TTS nie są MVP; jeśli będą potrzebne, preferować cloud, bo iMac może nie udźwignąć lokalnego audio.

---

## Sport: siatkówka, darmowo, bez kruchego scrapingu

### Źródło automatyczne nr 1: TheSportsDB free tier

TheSportsDB jest pierwszym kandydatem do automatyzacji, bo daje JSON i podstawowe endpointy działają dla reprezentacji Polski w siatkówce.

Sprawdzone identyfikatory / endpointy:

```text
Team: Poland Volleyball
idTeam: 141825

VNL men: idLeague=5083
EuroVolley men: idLeague=5613
World Championship men: idLeague=5344
Olympics Volleyball: idLeague=5042
```

Przykładowe endpointy:

```text
https://www.thesportsdb.com/api/v1/json/123/searchteams.php?t=Poland%20Volleyball
https://www.thesportsdb.com/api/v1/json/123/eventsnext.php?id=141825
https://www.thesportsdb.com/api/v1/json/123/eventslast.php?id=141825
https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id=5083
```

Caveats:

- Free tier może zwracać mało eventów.
- Dane są crowd-sourced, więc mogą być spóźnione albo niepełne.
- Nie traktować jako jedynego źródła prawdy.

### Official context / cross-check

Do weryfikacji i linkowania używać:

- **PZPS / Polska Siatkówka** — polski official context.
- **Volleyball World / VNL** — oficjalny międzynarodowy kontekst VNL.
- **CEV / EuroVolley** — oficjalny europejski kontekst.
- TVP Sport / Polsat Sport / Siatka.org — tylko jako human-readable linki lub ręczna weryfikacja.

Nie budować MVP na automatycznym scrapingu WP/SportoweFakty. Traktować takie serwisy jako linki dla człowieka, nie jako twarde źródło danych.

### Manual override jest obowiązkowy

Sportowe dane bywają spóźnione. Implementacja ma mieć plik:

```text
manual_sports_override.json
```

Użycie:

- Jurand może ręcznie wymusić najbliższy mecz albo poprawić wynik.
- Dashboard pokazuje, że dane są z override, nie udaje automatu.
- Override ma wyższy priorytet niż API, ale musi być oznaczony.

Minimalny kontrakt sportowy:

```json
{
  "schema_version": "1.0",
  "widget": "volleyball_matches",
  "status": "ok|stale|error|manual_needed|disabled",
  "source_status": "verified|single_source|conflict|manual_override|stale",
  "updated_at": "ISO-8601",
  "ttl_seconds": 3600,
  "sport": "volleyball",
  "team": "Poland",
  "competition": "VNL|EuroVolley|World Championship|Friendly|Other",
  "matches": [
    {
      "start_at": "ISO-8601",
      "home": "Poland Volleyball",
      "away": "Belgium Volleyball",
      "status": "scheduled|live|finished|postponed|unknown",
      "score": null,
      "source": "thesportsdb|manual|official_crosscheck"
    }
  ],
  "sources": [
    {
      "name": "TheSportsDB",
      "url": "https://www.thesportsdb.com/...",
      "checked_at": "ISO-8601"
    }
  ],
  "error": null
}
```

### Confidence policy

Dashboard nie ma udawać pewności:

- `verified` — official source i structured source się zgadzają.
- `single_source` — tylko jedno źródło działa.
- `manual_override` — Jurand/plik lokalny wymusił dane.
- `conflict` — źródła się różnią; pokazujemy ostrzeżenie.
- `stale` — dane stare.

---

## Voice: STT/TTS później, cloud-first jeśli iMac jest za słaby

### MVP

MVP NIE implementuje realnego audio.

MVP robi tylko:

- `voice_console.json`,
- mock transitions,
- LL / Pedro Voice Console UI,
- ręczny skrypt typu `mock-voice-result.py`.

### STT później

iMac ma mało RAM i może swapować, więc nie zakładać, że lokalne faster-whisper będzie praktyczne.

Preferowana kolejność testów:

1. **Groq Whisper STT** — jeśli Jurand podłączy Groq API; szybkie, cloud, OpenAI-compatible, dobre do krótkich polskich komend.
2. **xAI/Grok STT** — jeśli Jurand podłączy xAI/Grok API i konto ma audio endpoints.
3. **local faster-whisper** — tylko jako benchmark/fallback offline po stabilnym MVP.
4. OpenAI/Mistral — alternatywy płatne.

Konfiguracja docelowa, nie MVP:

```env
STT_PROVIDER=groq|xai|local|openai|mistral
STT_LANGUAGE=pl
GROQ_API_KEY=
XAI_API_KEY=
```

### TTS później

TTS nie jest wymagany w MVP. LL może pokazywać wynik tekstowo.

Jeżeli TTS będzie potrzebny:

1. xAI/Grok TTS — jeśli jakość/język PL i konto/API działają.
2. Edge TTS — darmowy fallback, ale jakość/sterowanie do sprawdzenia.
3. OpenAI/Mistral/inne — płatne alternatywy.

Konfiguracja docelowa:

```env
TTS_PROVIDER=xai|edge|openai|mistral|none
VOICE_OUTPUT=screen_only|screen_and_speech
```

### Wake phrase „hej Pedro”

Wake phrase nie jest MVP.

Najpierw:

1. static cockpit,
2. JSON contracts,
3. no-systemd durability,
4. manual/push-to-talk STT,
5. dopiero potem always-listening wake phrase.

Przed always-listening wymagany benchmark:

- CPU idle z daemonem wake-word,
- RAM/RSS,
- false positives,
- zachowanie w `private` i `guest`,
- możliwość szybkiego wyłączenia mikrofonu.

---

## API/key priority

### Early / important

- `GOOGLE_MAPS_API_KEY` — traffic/commute.
- Google OAuth token — Calendar.

### Free / low friction

- Open-Meteo — no key.
- TheSportsDB free API key `123` — sports MVP.
- Manual override JSON — zero API dependency.

### Later

- `GROQ_API_KEY` or `XAI_API_KEY` — cloud STT/TTS.
- Paid sports API — only if free sources are stale and widget becomes important.

---

## Implementation rule for Codex

Do not block dashboard MVP on perfect sports or voice integrations.

Correct order:

1. Build stable dashboard + JSON state.
2. Add TheSportsDB volleyball adapter.
3. Add manual override.
4. Add official source links/cross-check status.
5. Add cloud STT design.
6. Only later test real voice/audio.

If source data is missing or uncertain, write a clear `manual_needed` / `single_source` / `stale` state instead of inventing fixtures.
