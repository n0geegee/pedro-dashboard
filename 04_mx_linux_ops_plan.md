# 04 — MX Linux ops plan: no-systemd deployment

## Realia operacyjne

Zakładamy MX Linux desktop bez niezawodnego systemd user service. Nie opieramy MVP na `systemctl`, timerach systemd ani `journalctl`.

## Autostart i watchdog

Planowane mechanizmy:

1. **XDG autostart**
   - `~/.config/autostart/pedro-dashboard-server.desktop` uruchamia serwer dashboardu po loginie.
   - `~/.config/autostart/pedro-dashboard-kiosk.desktop` uruchamia Chrome/Chromium kiosk.
2. **Crontab fallback**
   - `@reboot` jako backup dla serwera/watchdoga.
   - `*/1 * * * *` albo `*/2 * * * *` watchdog check, jeśli XDG bywa zawodny.
3. **Watchdog shell scripts**
   - `start-dashboard.sh` — start serwera, log do `~/.local/state/pedro_dashboard/logs/`.
   - `stop-dashboard.sh` — bezpieczne zatrzymanie.
   - `status-dashboard.sh` — status procesu, portu, ostatnie health.
   - `start-kiosk.sh` — Chrome/Chromium `--kiosk http://127.0.0.1:<port>`.
   - `watchdog-dashboard.sh` — restartuje serwer/kiosk, jeśli health/port/browser padnie.
   - `install-autostart.sh` — instaluje `.desktop` i proponuje crontab.

To są pliki do późniejszej implementacji; ten katalog zawiera tylko plan.

## Chrome/Chromium kiosk

Docelowe flagi do rozważenia:

- `--kiosk http://127.0.0.1:17890/`
- `--no-first-run`
- `--disable-session-crashed-bubble`
- osobny profil browsera, np. `~/.local/share/pedro_dashboard/chrome-profile`;
- opcjonalnie `--autoplay-policy=no-user-gesture-required` dopiero gdy voice/TTS będzie potrzebne.

## Logi i stan

- Logi: `~/.local/state/pedro_dashboard/logs/`.
- Runtime state: `~/.local/state/pedro_dashboard/state/` albo projektowy `state/` podczas developmentu.
- Sekrety: nigdy w logach UI; konfiguracja przez `.env` lub plik mode bez ekspozycji w browserze.

## Health checks

Watchdog powinien sprawdzać:

- czy port dashboardu odpowiada `/api/health`;
- czy proces Python istnieje;
- czy Chrome/Chromium działa i ma właściwy URL;
- czy stan JSON nie jest starszy niż TTL × tolerancja;
- czy RAM/swap nie wskazuje na runaway process.

## Testy operacyjne przed uznaniem MVP za gotowe

1. Reboot/login: dashboard i kiosk wracają same.
2. Kill browser: watchdog przywraca kiosk.
3. Kill serwer: watchdog przywraca serwer.
4. Odłącz internet: UI działa w degraded/stale.
5. Zatrzymaj Hermes/OpenViking: panel TR pokazuje offline bez crasha.
6. Zmień privacy mode: LL i LR ukrywają treści zgodnie z macierzą.
7. Godzina pracy: RAM/swap stabilne, bez narastającego zużycia.
