# Pedro Dashboard — etapowy task list MVP

Updated: 2026-06-15T13:33:11+02:00

## Etap 0 — discovery/inventory (done)

- [x] Przeczytać plan lokalny w `/home/imac-hermes/projects/pedro_dashboard`.
- [x] Zweryfikować host/display/tools/ports/Hermes/OpenViking bez sekretów.
- [x] Zapisać `docs/host_inventory.md`.

## Etap 1 — minimalny cockpit skeleton

Owner: worker B, potem primary verification.

- [x] Utworzyć `app/server.py` — Python stdlib, bind default `127.0.0.1:17890`.
- [x] Utworzyć `app/static/index.html`, `styles.css`, `app.js` — 1920×1200, 2×2, no-scroll intent.
- [x] Utworzyć `app/state/` i mock JSON state.
- [x] Utworzyć `scripts/write-mock-state.py` i `scripts/mock-voice-result.py`.
- [x] Endpointy: `/`, `/api/health`, `/api/state`, `/api/voice_console`.
- [x] Verify: `py_compile`, mock writers, JSON validation, server + curl.

Verification snapshot:
- `python3 -m py_compile app/server.py scripts/write-mock-state.py scripts/mock-voice-result.py` → OK.
- `python3 scripts/write-mock-state.py && python3 scripts/write-mock-state.py --check` → 8 JSON files present/valid/fresh.
- `python3 scripts/mock-voice-result.py --quick 'hej Pedro, pokaż stan projektu'` → `speaking_or_result`.
- Server smoke: `/api/health`, `/api/state`, `/api/voice_console`, `/`, `/static/app.js` → HTTP 200 on `127.0.0.1:17890`.
- Negative checks: corrupt JSON becomes widget `error`; `POST /api/health` → 405; path traversal route not served.
- Codex xhigh final review → `NO_BLOCKING_FINDINGS`; Clawpatch blocked because project is not initialized (`clawpatch init` needed).

## Etap 2 — robust JSON/degraded UI

- [ ] Atomic write helper: temp + flush + `os.replace`.
- [ ] Missing/malformed JSON must not white-screen UI.
- [ ] Distinct widget statuses: `ok/stale/error/empty/disabled`.
- [ ] Voice mock transitions across required states.

## Etap 3 — safe health probes

- [x] RAM/swap/disk/uptime probe with timeout-safe subprocess or `/proc` reads.
- [x] Hermes gateway public status only, no raw logs.
- [x] OpenViking `/health` public status only.
- [x] Dashboard status self-probe.

## Etap 4 — no-systemd ops

- [x] `scripts/start-dashboard.sh`.
- [x] `scripts/stop-dashboard.sh`.
- [x] `scripts/status-dashboard.sh`.
- [x] `scripts/start-kiosk.sh` using `google-chrome` and dedicated profile.
- [x] `scripts/watchdog-dashboard.sh --once`.
- [x] `scripts/install-autostart.sh` writes XDG `.desktop` and shows crontab before modification.

Verification snapshot:
- `bash -n scripts/*.sh` equivalent focused check → OK for lifecycle/autostart scripts.
- `python3 -m py_compile` for probes/server/mock scripts → OK.
- `refresh-system-status.py`, `refresh-hermes-status.py`, `refresh-openviking-status.py` → wrote public-safe state JSON.
- `start-dashboard.sh` → server healthy on `127.0.0.1:17890`; `/api/state` all widgets `ok` after startup refresh.
- `PEDRO_PORT=17891 start-dashboard.sh` → server health OK on `17891`, then stopped cleanly.
- Tampered PID file pointing to unrelated `sleep` process → `stop-dashboard.sh` refused and did not kill it.
- `watchdog-dashboard.sh --once` restored stopped server in smoke test.
- `install-autostart.sh --print-only` showed XDG/crontab proposal without changes; cron apply path de-duplicates old Pedro entries.
- `start-kiosk.sh` exits `75` when backend health is down; DISPLAY-unreachable path remains nonfatal by design.
- Codex xhigh final review → `NO_BLOCKING_FINDINGS`; Clawpatch still blocked until `clawpatch init` / git repo decision.

## Etap 5 — privacy hardening

- [x] Explicit `DASHBOARD_PRIVACY_MODE=normal|private|guest`.
- [x] Backend/state redaction before frontend sees data for voice console MVP.
- [x] Guest/private fixtures prove transcript/result command details are hidden in voice console.

## Etap 6 — QA closeout

- [ ] Browser/screenshot visual check at 1920×1200 if session permits.
- [ ] Kill server -> watchdog restore.
- [ ] Kill Chrome -> watchdog restore, if kiosk session available.
- [ ] No systemd dependency in scripts.
- [ ] Codex xhigh review and Clawpatch review, or honest blocker output.

## Later, not MVP blocker

- [ ] Open-Meteo/weather.
- [ ] TheSportsDB volleyball + `manual_sports_override.json`.
- [ ] Google Maps/Calendar after credentials and quotas are explicit.
- [ ] Voice phase B design/push-to-talk; no wake-word until benchmark.
