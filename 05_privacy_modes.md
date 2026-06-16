# 05 — Privacy modes

## Tryby

Konfiguracja runtime:

```text
DASHBOARD_PRIVACY_MODE=normal|private|guest
```

## Definicje

- **normal** — pełny cockpit dla właściciela; nadal bez sekretów i raw logów.
- **private** — tryb domowy, gdy ekran jest widoczny dla innych; statusy tak, treści prywatne nie.
- **guest** — tryb gości; tylko neutralne informacje: czas, pogoda/status ogólny, zdrowie systemu bez szczegółów.

## Macierz widoczności

| Dane | normal | private | guest |
|---|---:|---:|---:|
| Godzina/data | tak | tak | tak |
| RAM/disk/uptime | tak | tak | ogólnie |
| Hermes gateway online/offline | tak | tak | ogólnie |
| OpenViking health | tak | tak | ogólnie |
| Nazwy prywatnych projektów | tak/skrót | ukryj albo pseudonim | nie |
| Pełne wiadomości Discord/email | nie w MVP | nie | nie |
| Prompty/raw agent output | nie | nie | nie |
| Tokeny/API keys/sekretne ścieżki | nigdy | nigdy | nigdy |
| Pedro transkrypcja | skrót | ukryj/skrót | nie |
| Pedro wynik komendy | skrót bez sekretów | status bez treści | nie |
| Błędy debug | `debug_ref` tylko | `debug_ref` tylko | ogólny komunikat |

## Zasady redakcji

- UI dostaje już przefiltrowane dane; frontend nie jest jedyną linią obrony.
- Każdy widget ma znać `privacy_mode` i sam decydować o publicznym tekście.
- OpenViking/Hermes integracje zwracają dashboardowi streszczenia, nie raw dokumenty.
- Błędy pokazują `message_public`, a szczegóły trafiają tylko do logów lokalnych.
- W trybie guest voice może być `disabled` albo tylko `idle/listening unavailable`.

## Privacy acceptance tests

- W `guest` nie widać transkrypcji Pedro ani nazw prywatnych projektów.
- W `private` nie widać pełnych wypowiedzi użytkownika.
- W żadnym trybie nie widać tokenów, ścieżek `.env`, fragmentów raw logów ani promptów.
- Przełączenie trybu działa bez restartu browsera, jeśli state polluje konfigurację.
