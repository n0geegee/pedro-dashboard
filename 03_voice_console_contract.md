# 03 — Pedro Voice Console contract

## Rola panelu LL

LL / lower-left w layout 2×2 jest zawsze zarezerwowany dla **Pedro Voice Console**. W MVP to nie jest jeszcze produkcyjny wake-word system; to widoczny panel i kontrakt danych, który później podłączymy do audio/STT/Hermes runnera.

## Stany UX

Panel musi obsługiwać:

- `disabled` — voice nieuruchomiony lub tryb guest blokuje aktywne słuchanie;
- `idle` — gotowy, ale nie słucha aktywnie;
- `listening_for_wake` — czeka na „hej Pedro”;
- `wake_detected` — wykryto frazę, krótka animacja/confirmation;
- `recording` — zbiera wypowiedź po wake phrase;
- `transcribing` — STT;
- `thinking` — Hermes runner przygotowuje odpowiedź;
- `searching` — Hermes/OpenViking wykonuje lookup;
- `needs_clarification` — Pedro pyta doprecyzowująco;
- `speaking_or_result` — wynik komendy/odpowiedź;
- `error` — błąd audio/STT/Hermes/privacy;
- `privacy_blocked` — treść ukryta przez `private` albo `guest`.

## Kontrakt `voice_console.json`

Planowany plik stanu:

```json
{
  "status": "ok|stale|error|disabled",
  "updated_at": "ISO-8601",
  "ttl_seconds": 10,
  "privacy_mode": "normal|private|guest",
  "voice": {
    "mode": "mock|wake_word|push_to_talk|disabled",
    "state": "idle|listening_for_wake|wake_detected|recording|transcribing|thinking|searching|needs_clarification|speaking_or_result|error|privacy_blocked",
    "wake_phrase": "hej Pedro",
    "mic_status": "unknown|available|muted|missing|error",
    "stt_status": "not_configured|ready|busy|error",
    "runner_status": "not_configured|ready|busy|error"
  },
  "utterance": {
    "partial": "",
    "final": "",
    "language": "pl",
    "confidence": null
  },
  "activity": {
    "label": "Słucham / Myślę / Szukam / Gotowe",
    "detail": "krótki tekst bez sekretów",
    "spinner": true
  },
  "result": {
    "summary": "krótki wynik do pokazania na ekranie",
    "requires_user_action": false,
    "clarifying_question": null
  },
  "error": {
    "code": null,
    "message_public": null,
    "debug_ref": null
  }
}
```

## Zasady prywatności dla voice panelu

- `normal`: można pokazać skróconą transkrypcję i wynik, ale nadal bez sekretów/raw logs.
- `private`: pokazuj statusy i bardzo krótkie streszczenia; ukrywaj pełną transkrypcję i treści prywatne.
- `guest`: nie pokazuj transkrypcji ani wyników osobistych; panel może pokazywać „Pedro dostępny / niedostępny”.

## Fazy rozwoju voice

### Faza A — MVP mock

- JSON kontrakt + ręczne/mock aktualizacje stanów.
- Testy UI: idle → wake_detected → transcribing → thinking → result → error/privacy.
- Żadnego mikrofonu jako zależności release.

### Faza B — push-to-talk lub manual trigger

- Bez wake-word, ale realna ścieżka: nagranie krótkiej komendy → STT → wpis do `voice_console.json`.
- Pozwala testować STT/Hermes bez fałszywych wake detections.

### Faza C — wake phrase „hej Pedro”

- Lokalny wake-word dopiero po sprawdzeniu CPU/RAM.
- Wymagane decyzje: silnik wake-word, mikrofon, język PL, false positives, tryb guest/private.

### Faza D — Hermes runner

- Komenda po STT trafia do kontrolowanego runnera Hermes/gateway.
- Runner musi mieć limity czasu, allowlistę komend i publiczny status do UI.
- OpenViking używany do lookupów/statusu, nie do wyświetlania prywatnych źródeł raw.
