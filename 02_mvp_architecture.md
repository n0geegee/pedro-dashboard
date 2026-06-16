# 02 — MVP architecture

## Zakres MVP

MVP ma dostarczyć stabilny cockpit działający cały dzień na iMacu:

- lokalny serwer Python na `127.0.0.1:<port>`;
- statyczny frontend HTML/CSS/vanilla JS;
- layout 2×2 pod 1920×1200;
- odświeżanie przez fetch JSON co kilka sekund;
- pliki stanu JSON z atomowym zapisem;
- mock źródła dla Pedro Voice Console;
- health probes dla Hermes gateway, OpenViking i systemu;
- tryby privacy `normal/private/guest`.

## Docelowy katalog implementacji

Plan sugeruje późniejszą strukturę, ale w tym etapie nie tworzymy kodu:

```text
pedro_dashboard/
  README.md
  docs/plans/*.md
  app/
    server.py              # lekki HTTP server Python stdlib albo Flask dopiero jeśli konieczne
    static/index.html
    static/app.js
    static/styles.css
    state/*.json
    scripts/*.sh
    logs/
```

W obecnym katalogu projektu znajdują się tylko markdowni planu.

## Komponenty MVP

### 1. Dashboard server

- Preferowany start: Python stdlib `http.server`/`ThreadingHTTPServer` + własne endpointy.
- Port domyślny: np. `17890`, bind do `127.0.0.1` dla kiosk-only; LAN bind dopiero świadomie.
- Endpointy planowane:
  - `/` → statyczny cockpit;
  - `/api/state` → złożony stan paneli;
  - `/api/voice_console` → bezpośredni stan LL;
  - `/api/health` → health serwera dashboardu.

### 2. Frontend

- Czysty HTML/CSS/vanilla JS.
- Zero build step, zero Node.
- CSS grid 2×2 z wymiarami dobranymi do 1920×1200.
- Każdy panel pokazuje `ok/stale/error/empty/disabled`.
- UI nie crashuje przy brakującym lub częściowo uszkodzonym JSON.

### 3. State layer

Każdy widget ma osobny stan albo jeden agregat, ale z tym samym kontraktem:

```json
{
  "status": "ok|stale|error|empty|disabled",
  "updated_at": "ISO-8601",
  "ttl_seconds": 60,
  "privacy_mode": "normal|private|guest",
  "data": {},
  "error": null
}
```

Zapisy muszą być atomowe:

1. zapisz do pliku tymczasowego w tym samym katalogu;
2. flush/fsync tam, gdzie ma sens;
3. `rename` na plik docelowy;
4. frontend traktuje stare dane jako `stale`, nie jako fatal error.

### 4. Integracje systemowe

- RAM/swap/disk/uptime: krótkie, timeoutowane sondy.
- Hermes gateway: status procesu/logiczny health, ale bez raw logów w UI.
- OpenViking: health/search availability, bez pokazywania prywatnych wyników bez filtra privacy.
- Chrome kiosk: kontrolowany osobnym skryptem i watchdogiem.

## Dlaczego bez Node na starcie

- 5.8 GB RAM + stary iMac = mniej miejsca na Electron/Node watcher/build tooling.
- MVP ma być niezawodny po reboot/kill/offline, nie designersko ciężki.
- Vanilla JS wystarczy do fetch/render/status cards.
- Node można dodać w fazie 4 dopiero po stabilnym MVP i pomiarach RAM.
