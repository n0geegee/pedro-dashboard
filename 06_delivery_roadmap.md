# 06 — Delivery roadmap

## Faza 0 — decyzje i pomiar hosta

- Potwierdzić canonical path: `/linus1/hermes/projects/pedro_dashboard` jako projekt, user-facing nazwa `/pedro_dashboard`.
- Potwierdzić Chrome vs Chromium i ścieżkę binarki.
- Potwierdzić port, np. `17890`.
- Zweryfikować rozdzielczość 1920×1200 na iMacu.
- Spisać, czy Hermes gateway i OpenViking działają lokalnie czy przez LAN.

**Exit criteria:** wiadomo gdzie uruchamiamy, jaki browser, jaki port, jakie health endpointy.

## Faza 1 — static cockpit MVP

- Utworzyć lekki serwer Python + statyczny frontend.
- Zbudować layout 2×2 dla 1920×1200.
- Wprowadzić state JSON z TTL/status/error.
- Dodać mock data dla wszystkich paneli.
- Dodać `voice_console.json` mock transitions.

**Exit criteria:** lokalny browser pokazuje dashboard, LL przechodzi przez mock stany Pedro.

## Faza 2 — real health probes

- Dodać timeoutowane sondy RAM/swap/disk/uptime.
- Dodać Hermes gateway health/status bez raw logs.
- Dodać OpenViking health/status bez prywatnych treści.
- Dodać degraded/stale rendering.

**Exit criteria:** zatrzymanie Hermes/OpenViking nie psuje UI; statusy są prawdziwe.

## Faza 3 — no-systemd durability

- Dodać start/stop/status/watchdog scripts.
- Dodać XDG autostart `.desktop` dla serwera i kiosku.
- Dodać crontab fallback.
- Przetestować reboot, kill browser, kill server, offline.

**Exit criteria:** cockpit sam wraca i działa godzinę bez wzrostu RAM/swap.

## Faza 4 — voice pipeline bez wake-word

- Podłączyć manual/push-to-talk trigger albo mock CLI do realnego STT.
- Wpisywać wyniki do `voice_console.json` atomowo.
- Dodać Hermes runner w trybie allowlist/timeout.
- Obsłużyć clarifying question i public error messages.

**Exit criteria:** jedna krótka polska komenda przechodzi audio/manual → STT → Hermes status/result → UI.

## Faza 5 — wake phrase „hej Pedro”

- Wybrać lokalny wake-word engine po teście CPU/RAM.
- Ustawić false positive policy i privacy behavior.
- Dopiero po stabilizacji dodać always-listening.

**Exit criteria:** wake phrase działa stabilnie, nie mieli RAM/CPU i respektuje private/guest.

## Faza 6 — polish i rozszerzenia

- Delikatne animacje, TTS, lepsze alerty.
- Ewentualnie Node/React tylko jeśli MVP stabilny i jest realna potrzeba.
- Więcej integracji dopiero po privacy review.
