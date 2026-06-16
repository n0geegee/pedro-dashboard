# 01 — Product outline: Pedro Dashboard

## Jednozdaniowa wizja

Pedro Dashboard to zawsze widoczny **room cockpit** dla domu/pracy Juranda: status systemu, fokusu i decyzji, a w lewym dolnym panelu interfejs głosowy Pedro, który docelowo reaguje na „hej Pedro”.

## Layout 1920×1200, 2×2

Projektujemy natywnie pod 16:10, nie 1080p.

- **TL / top-left — Now / Focus**
  - godzina, data, aktualny focus, następny krok;
  - status: „spokojnie”, „uwaga”, „pilne”.
- **TR / top-right — Hermes / Ops**
  - Hermes gateway online/offline;
  - OpenViking health;
  - RAM/swap/disk/uptime;
  - watchdog/kiosk status.
- **LL / lower-left — Pedro Voice Console**
  - centralny panel rozmowy i komend;
  - status nasłuchu/wake phrase;
  - transkrypcja, thinking/searching, wynik, pytanie doprecyzowujące;
  - błędy i privacy banner.
- **LR / lower-right — Queue / Decisions / Alerts**
  - pending decisions;
  - najbliższe alerty;
  - ewentualnie krótkie zadania/kanban summary, bez prywatnych treści w trybie guest/private.

## Kluczowe scenariusze użycia

1. **Rzut oka z pokoju:** widzę czy Hermes, OpenViking i iMac są zdrowe.
2. **Tryb rodzinny/gość:** dashboard nie zdradza prywatnych wiadomości, promptów ani ścieżek sekretów.
3. **Pedro voice ready:** LL pokazuje, czy system słucha, co usłyszał i co robi.
4. **Awaria bez paniki:** brak internetu/Hermes/OpenViking nie robi białego ekranu; pokazuje stale/degraded.
5. **Restart/reboot:** po zalogowaniu do MX Linux kiosk sam wraca.

## Non-goals dla MVP

- Brak React/Vite/Next/Electron/Node.
- Brak produkcyjnego wake-word w pierwszym etapie.
- Brak OAuth-heavy integracji typu Google Calendar/Photos w pierwszym etapie.
- Brak wyświetlania raw logów, promptów, tokenów, prywatnych wiadomości.
- Brak założenia, że systemd działa.
