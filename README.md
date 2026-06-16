# pedro_dashboard — always-on iMac-Hermes room cockpit

**Cel projektu:** zbudować lekki, zawsze włączony dashboard pokojowy na starym iMacu z MX Linux, działający w Chrome/Chromium kiosk na ekranie **1920×1200**, z panelem **LL / lower-left** jako przyszłą **Pedro Voice Console** aktywowaną frazą „hej Pedro”.

To jest **plan wdrożenia, nie kod**. MVP ma powstać bez Node/Electron/React: **Python + static HTML/CSS + vanilla JS**, lokalny stan w JSON zapisywany atomowo, uruchamianie bez systemd przez XDG autostart + crontab/watchdog.

## Założenia bazowe

- Host: stary iMac / MX Linux / brak pewnego systemd.
- RAM: ok. **5.8 GB**, więc pierwsza wersja musi być lekka i odporna na swap.
- Ekran: **1920×1200, 16:10**, projektowany jako cockpit widoczny z pokoju.
- Browser: Chrome/Chromium w trybie kiosk na `http://127.0.0.1:<port>`.
- Backend MVP: jeden lekki proces Python, statyczne assety, brak Node na starcie.
- Integracje: Hermes gateway, OpenViking, lokalne sondy systemowe; bez wyświetlania sekretów/logów raw.
- Voice: MVP robi **UI + kontrakt `voice_console.json` + mock scripts**; wake-word/STT/Hermes runner dopiero w kolejnych fazach.

## Pliki planu

1. `README.md` — skrót projektu i mapa dokumentów.
2. `00_prompt_dla_pedro_start_HERE.md` — START HERE: gotowy prompt dla iMac-Hermes/Pedro primary.
3. `00_MASTER_PLAN.md` — główny xhigh plan implementacyjny, taski, kontrakty, akceptacja.
4. `01_product_outline.md` — wizja, layout 2×2, role paneli, scenariusze użycia.
5. `02_mvp_architecture.md` — architektura MVP, katalogi docelowe, kontrakty JSON, brak Node.
6. `03_voice_console_contract.md` — szczegółowy kontrakt Pedro Voice Console i fazy audio.
7. `04_mx_linux_ops_plan.md` — uruchamianie bez systemd: XDG autostart, Chrome kiosk, crontab/watchdog.
8. `05_privacy_modes.md` — tryby `normal/private/guest`, redakcja i zasady room-visible UI.
9. `06_delivery_roadmap.md` — fazy wdrożenia i kryteria akceptacji.
10. `07_blocking_risks.md` — ryzyka blokujące, decyzje do podjęcia, mitigacje.
11. `08_CODEX_PROMPTS.md` — gotowe prompty do sekwencyjnej pracy Codexa/iMac-Hermes.
12. `09_QA_ACCEPTANCE.md` — checklisty QA dla UI, privacy, no-systemd, watchdoga i voice panelu.
13. `10_APIS_AND_TOOLS.md` — wymagane API, źródła danych i rekomendacja dla sportu/Google/voice.
14. `11_FREE_FIRST_VOLLEYBALL_AND_VOICE_GUIDANCE.md` — twarde wskazówki: siatkówka/PZPS, darmowe źródła, Groq/Grok voice later.
15. `PROJECT_DECISIONS.md` — locked/pending/future decisions dla projektu.
16. `PLAN_FILES_SUMMARY.md` — krótka mapa plików.

## Najważniejsze sekcje do przeczytania najpierw

- **Start dla Pedro/iMac-Hermes:** `00_prompt_dla_pedro_start_HERE.md`.
- **Master handoff:** `00_MASTER_PLAN.md`.
- **MVP scope:** `02_mvp_architecture.md` → „Zakres MVP”.
- **LL jako Pedro Voice Console:** `03_voice_console_contract.md` → „Kontrakt `voice_console.json`”.
- **No-systemd launch:** `04_mx_linux_ops_plan.md` → „Autostart i watchdog”.
- **Privacy:** `05_privacy_modes.md` → „Macierz widoczności”.
- **Codex prompts:** `08_CODEX_PROMPTS.md`.
- **QA:** `09_QA_ACCEPTANCE.md`.
- **APIs/tools:** `10_APIS_AND_TOOLS.md`.
- **Free-first volleyball/voice:** `11_FREE_FIRST_VOLLEYBALL_AND_VOICE_GUIDANCE.md`.
- **Blocking risks:** `07_blocking_risks.md`.
