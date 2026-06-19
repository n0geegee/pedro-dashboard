# Pedro Dashboard v1.4.9 — always-listening KWS voice daemon

Released: 2026-06-19 by Pedro (iMac-Hermes).

## What changed

### NEW: `scripts/pedro_voice_kws.py` (517 lines)

Always-listening "hey pedro" keyword-spotting daemon. Pipeline:
1. **Vosk** streams 16 kHz PCM from `PEDRO_MIC` (`plughw:0,2`).
2. On "hey pedro" wake phrase → switch to command-listening mode for
   `PEDRO_VOICE_KWS_COMMAND_SECONDS` (default 4.0 s).
3. **Gemini** receives the buffered audio + transcript and returns a
   structured command (function-calling JSON over the Gemini API).
4. **Runner** dispatches the command (open URL, set state, run script).
5. **espeak-ng** speaks the response out loud via the same audio device.

Replaces the v1.3 push-to-talk daemon (which polled the X keyboard
and required a physical Space keypress — impossible on this kiosk
which has no keyboard, only a mouse attached).

### NEW: `scripts/start-voice-kws.sh` (88 lines)

- Sources `scripts/_lifecycle_common.sh` for env vars.
- Daemonises `pedro_voice_kws.py` with nohup, writes PID to
  `$PEDRO_RUN_DIR/voice_kws.pid`, logs to `$PEDRO_LOG_DIR/voice_kws.log`.
- Usage: `scripts/start-voice-kws.sh [--start|--stop|--status|--restart]`.

### NEW: `scripts/stop-voice-kws.sh` (30 lines)
### NEW: `scripts/status-voice-kws.sh` (18 lines)

Standard start/stop/status triad for the KWS daemon. Symmetric to
the v1.3 push-to-talk scripts (which still ship for fallback).

### `scripts/_lifecycle_common.sh` (KWS env block, already staged in v1.4.8)

- `PEDRO_VOICE_KWS_SCRIPT` — path to the daemon.
- `PEDRO_VOICE_KWS_PID_FILE` / `_LOG_FILE` — runtime files.
- `PEDRO_VOSK_MODEL` — model dir (default `~/.local/share/vosk/models/small-pl`).
- `PEDRO_VOICE_KWS_COMMAND_SECONDS` — wake-to-command window.
- `PEDRO_AUTOSTART_VOICE_KWS_FILE` — `.desktop` path (autostart wiring
  to be added by a follow-up v1.4.10 if needed).
- `PEDRO_MIC_DEVICE` — hardcoded `plughw:0,2` (ALC889A Alt Analog on this iMac).
- `PEDRO_VOICE_PY_BIN` — migrated from `$HOME/.local/share/pedro-voice-venv/bin/python`
  to `$PEDRO_PROJECT_ROOT/.venv-voice/bin/python` (venv moved into the project
  for repo-portability).

### `scripts/watchdog-dashboard.sh` (+~25 lines)

Adds a KWS daemon health check loop with the same hourly restart budget
used for the dashboard HTTP and the v1.3 push-to-talk daemon. Watches
the KWS PID file and resurrects the daemon when it dies, unless the
restart budget is exhausted (then it backs off and logs).

### `scripts/write-mock-state.py` (-7 lines)

Drops `voice_console.json` from the mock baseline. The KWS daemon
owns that widget exclusively; the previous mock entry caused visible
races where the 20 s refresher briefly flashed mock values before
the live daemon overwrote them.

## Dependencies (all verified by Codex audit)

| Dep | Path | Status |
|---|---|---|
| Vosk model | `~/.local/share/vosk/models/small-pl/` | ✅ present |
| Project venv | `projects/pedro_dashboard/.venv-voice/` | ✅ present |
| Legacy venv | `~/.local/share/pedro-voice-venv/` | ✅ still works |
| Mic `plughw:0,2` | `arecord -D plughw:0,2 -d 1 ...` | ✅ 32044 B wav |

## Caveats (Codex audit)

- **No autostart `.desktop` yet** — daemon won't auto-start on boot
  until `scripts/install-autostart.sh` is updated to call
  `start-voice-kws.sh`. v1.4.10 candidate.
- **KWS daemon is "complete but unproven"** — no evidence of an
  overnight run on the kiosk. Smaller atomic release makes
  rollback easier if Jurand reports wake-phrase false-positives.
- **No conflict with v1.3 push-to-talk** — both daemons can run
  side-by-side; the watchdog manages each independently.

## What did NOT change

- All v1.4.7 (VNL TZ) + v1.4.8 (photos) code is untouched.
- `app/server.py`, frontend, kiosk Chrome, all release notes — unchanged.
- Voice console widget contract (`voice_console.json` schema) — unchanged.

## Rollback

```bash
git checkout v1.4.8 -- scripts/_lifecycle_common.sh \
                       scripts/watchdog-dashboard.sh \
                       scripts/write-mock-state.py
rm -f scripts/pedro_voice_kws.py \
      scripts/start-voice-kws.sh \
      scripts/stop-voice-kws.sh \
      scripts/status-voice-kws.sh
# Stop the daemon if running
scripts/stop-voice-kws.sh 2>/dev/null || true
```

## Related

- v1.4.7 release note: `docs/releases/PEDRO_DASHBOARD_V1.4.7.md`
- v1.4.8 release note: `docs/releases/PEDRO_DASHBOARD_V1.4.8.md`
- Codex audit: see Pedro session log 2026-06-19 18:45-19:10
- Recovery plan: `~/.hermes/state/pedro-dashboard-recovery-plan.md`