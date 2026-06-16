# 08 — Prompty dla Codexa / iMac-Hermes

Use these prompts sequentially. Do not give all at once. After each prompt, verify on the actual iMac where possible.

---

## Prompt 0 — inventory only

```text
You are working on /linus1/hermes/projects/pedro_dashboard.
Do not write application code yet.
Create docs/host_inventory.md with live host facts for iMac-Hermes:
- OS and no-systemd status;
- browser binary path;
- DISPLAY/xrandr resolution;
- RAM/swap/disk;
- Python version;
- Hermes status summary without secrets;
- OpenViking health summary without private data.

Do not print or store secrets. Do not use systemctl as a required path.
```

---

## Prompt 1 — lightweight static MVP skeleton

```text
Build the first Pedro Dashboard MVP skeleton.
Constraints:
- no React, no Vite, no Node, no Electron;
- Python local server + static HTML/CSS/vanilla JS;
- bind to 127.0.0.1:17890;
- target layout 1920x1200;
- LL panel is Pedro Voice Console.

Create:
- app/server.py
- app/static/index.html
- app/static/styles.css
- app/static/app.js
- app/state/
- scripts/write-mock-state.py
- scripts/mock-voice-result.py

Implement /api/health, /api/state, /api/voice_console.
Use mock JSON state files only. No real audio yet.
Verify with curl and python JSON validation.
```

---

## Prompt 2 — state contracts and degraded UI

```text
Implement atomic JSON writes and robust state loading.
Every widget must show ok/stale/error/empty/disabled.
Missing or malformed JSON must not white-screen the UI.
Add mock transitions for voice_console:
idle -> listening_for_wake -> wake_detected -> recording -> transcribing -> thinking -> searching -> speaking_or_result -> error -> privacy_blocked.

No secrets, no raw logs, no private Discord content.
Verify by deliberately corrupting one JSON file and showing degraded state.
```

---

## Prompt 3 — real health probes

```text
Add lightweight probes for:
- RAM/swap/disk/uptime;
- dashboard process/health;
- Hermes gateway status without raw logs;
- OpenViking health without private data.

All probes need 1-3 second timeouts and sanitized public output.
Write results atomically to state/*.json.
Do not add agent/LLM calls for routine refreshes.
```

---

## Prompt 4 — MX Linux no-systemd durability

```text
Implement no-systemd lifecycle scripts:
- scripts/start-dashboard.sh
- scripts/stop-dashboard.sh
- scripts/status-dashboard.sh
- scripts/start-kiosk.sh
- scripts/watchdog-dashboard.sh
- scripts/install-autostart.sh

Use XDG autostart and optional crontab fallback.
Do not depend on systemctl, systemd timers, or journalctl.
Use logs under ~/.local/state/pedro_dashboard/logs/ and pid files under ~/.local/state/pedro_dashboard/run/.
Chrome kiosk should use a dedicated profile directory and open http://127.0.0.1:17890/.
```

---

## Prompt 5 — privacy modes

```text
Add DASHBOARD_PRIVACY_MODE normal|private|guest.
Default must be explicit in config.
Rules:
- normal: show safe summaries, no raw secrets/logs;
- private: hide full transcript and personal content;
- guest: show only generic status, clock, and non-sensitive availability.

Pedro Voice Console must respect privacy before content reaches the frontend.
Add tests/manual fixtures proving guest/private hide transcript and result details.
```

---

## Prompt 6 — voice phase B design

```text
Do not implement wake-word yet.
Create docs/voice_phase_b_design.md for manual/push-to-talk voice command pipeline:
manual trigger -> record short utterance -> STT -> controlled Hermes runner -> voice_console.json -> LL result.
Compare local faster-whisper vs cloud STT options for Polish, CPU/RAM, latency, privacy and cost.
Define command allowlist, timeouts, result redaction, and debug_ref policy.
```
