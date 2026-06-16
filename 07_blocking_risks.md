# 07 — Blocking risks and decisions

## Blocking risks

1. **Niepewny systemd na MX Linux**
   - Ryzyko: plan oparty o `systemctl` nie wystartuje po reboot.
   - Mitigacja: XDG autostart + crontab/watchdog jako ścieżka podstawowa.

2. **RAM 5.8 GB i stary iMac**
   - Ryzyko: Electron/Node/watchery albo ciężki wake-word/STT powodują swap.
   - Mitigacja: Python + static HTML/vanilla JS; Node dopiero po pomiarach; godzinny soak test.

3. **Wake-word PL „hej Pedro” może być trudny/stale aktywny**
   - Ryzyko: false positives, obciążenie CPU, prywatność w pokoju.
   - Mitigacja: MVP bez wake-word; najpierw UI contract + mock, potem push-to-talk, potem wake-word.

4. **Room-visible privacy**
   - Ryzyko: dashboard przypadkiem pokaże prywatne wiadomości, prompt, ścieżkę sekretu albo raw log.
   - Mitigacja: trzy tryby privacy, backend redaction przed frontendem, brak raw logs w UI.

5. **Hermes gateway/OpenViking health nie ma stabilnego endpointu**
   - Ryzyko: dashboard myli status albo wymaga parsowania niestabilnych logów.
   - Mitigacja: zdefiniować minimalne health probes; jeśli brak endpointu, użyć procesu/portu + public summary file.

6. **Atomic JSON state niedopilnowany**
   - Ryzyko: frontend czyta pół-zapisany plik i robi white screen.
   - Mitigacja: tmp + rename, TTL, schema defaults, degraded rendering.

7. **Chrome kiosk / autostart zależny od desktop session**
   - Ryzyko: po reboot nie ma loginu albo XDG nie odpala.
   - Mitigacja: potwierdzić auto-login/session; crontab/watchdog jako fallback; osobny status script.

8. **Port/bind i LAN exposure**
   - Ryzyko: cockpit z prywatnymi statusami wystawiony w LAN.
   - Mitigacja: MVP bind `127.0.0.1`; LAN dopiero po privacy review i ewentualnym auth/reverse proxy.

## Decyzje blokujące przed implementacją

- Czy projekt fizycznie ma żyć pod `/linus1/hermes/projects/pedro_dashboard` czy user wymaga rootowego `/pedro_dashboard` alias/symlink?
- Chrome czy Chromium i jaka ścieżka binarki na iMacu?
- Czy dashboard jest wyłącznie lokalny na iMacu (`127.0.0.1`), czy ma być dostępny z LAN?
- Jak sprawdzać Hermes gateway health: port/API/logiczny status/watchdog file?
- Jak sprawdzać OpenViking health na tym hoście?
- Czy `guest` ma całkowicie wyłączać nasłuch Pedro, czy tylko ukrywać transkrypcję?
- Jaki port domyślny rezerwujemy: proponowane `17890`.

## P1 risks po starcie MVP

- Fałszywe poczucie bezpieczeństwa przez samą redakcję frontendową.
- Narastające logi/state files bez rotacji.
- Zbyt częste polling/probes obciążające CPU.
- Brak wizualnego rozróżnienia `stale` vs `ok`.
- Brak testu offline powodujący białe ekrany przy awarii sieci.
