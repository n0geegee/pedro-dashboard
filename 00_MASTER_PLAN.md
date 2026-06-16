# Pedro Dashboard — xhigh master implementation plan

> **For Hermes/Codex:** implement task-by-task. Do not jump to React/Electron/wake-word before the static cockpit + JSON contracts + no-systemd durability are verified on the actual iMac.

**Goal:** Build an always-on iMac-Hermes room cockpit for 1920×1200 Chrome kiosk, with LL reserved as **Pedro Voice Console** for future wake phrase `hej Pedro` and voice-command results.

**Architecture:** Lightweight local Python server serves static HTML/CSS/vanilla JS and exposes JSON state endpoints. State is written atomically to local JSON files. MX Linux deployment uses XDG autostart + crontab/watchdog, not systemd. Voice is phased: mock UI/contract first, then manual/push-to-talk STT, then wake phrase, then controlled Hermes runner.

**Tech Stack MVP:** Python stdlib HTTP server or minimal Flask only if necessary; static HTML/CSS/vanilla JS; Chrome/Chromium kiosk; shell scripts; crontab; JSON state files.

---

## Non-negotiable constraints

1. **Target host:** iMac-Hermes, MX Linux/no-systemd, LAN `192.168.0.45`.
2. **Screen:** primary layout target `1920×1200`, no scroll in kiosk.
3. **Resource budget:** old iMac, ~5.8 GiB RAM, swap may already be used. No Electron/React/Node watcher in MVP.
4. **Runtime:** Chrome/Chromium kiosk on `http://127.0.0.1:17890/` unless explicitly changed.
5. **Visibility:** room-visible dashboard. No raw Discord, no raw logs, no prompts, no tokens, no secret paths.
6. **Durability:** no `systemctl`, no systemd timers, no `journalctl` dependency.
7. **LL meaning:** lower-left panel is **Pedro Voice Console**, not TBD.
8. **Voice scope:** MVP has `voice_console.json` + mock state transitions; no always-listening wake-word in MVP.

---

## Target UX layout — 1920×1200

### Header / top band

- Pedro/Hermes status name.
- Current time/date.
- Privacy mode indicator: `normal`, `private`, `guest`.
- Sync freshness indicator.
- Small global alert light: OK / stale / action needed.

### Main grid 2×2

#### UL — Today / Focus / Ops Summary

Purpose: quick glance from across the room.

MVP content:
- current focus;
- next 1–3 planned things;
- last successful dashboard refresh;
- simple weather/clock only if low-risk.

#### UR — System + Hermes Health

Purpose: know if the machine/agent stack is alive.

MVP content:
- RAM/swap/disk/uptime;
- dashboard server health;
- Hermes gateway health;
- Discord gateway status if detectable;
- OpenViking health;
- stale/error cards, never raw logs.

#### LL — Pedro Voice Console

Purpose: visible interface for `hej Pedro` voice interaction.

MVP states shown from mock JSON:
- idle / waiting;
- listening for wake;
- wake detected;
- recording;
- transcribing;
- thinking/searching;
- needs clarification;
- result;
- error;
- privacy blocked.

Future behavior:
`local wake-word -> record short utterance -> STT -> controlled Hermes runner/OpenViking lookup -> atomic voice_console.json -> LL result`.

#### LR — Ambient / Result Context / Photo Later

Purpose: secondary visual field.

MVP content:
- safe ambient placeholder or recent safe status;
- optionally latest non-sensitive command result context;
- Photos/slideshow only later after privacy and resource review.

---

## State contracts

Every state file uses this base envelope:

```json
{
  "schema_version": "1.0",
  "widget": "system_status",
  "status": "ok|stale|error|empty|disabled",
  "updated_at": "2026-06-15T12:00:00+02:00",
  "ttl_seconds": 60,
  "privacy_mode": "normal|private|guest",
  "source": "local-probe",
  "data": {},
  "error": null
}
```

Required MVP files:

```text
state/dashboard_status.json
state/system_status.json
state/hermes_status.json
state/openviking_status.json
state/current_focus.json
state/alerts.json
state/decisions.json
state/voice_console.json
```

Atomic write rule:

1. write to `filename.tmp.<pid>` in same directory;
2. flush and close;
3. `os.replace(tmp, target)`;
4. reader treats missing/bad/stale file as degraded state, not fatal error.

---

## Voice console contract summary

See `03_voice_console_contract.md` for full detail. Minimum useful shape:

```json
{
  "schema_version": "1.0",
  "widget": "voice_console",
  "status": "ok",
  "updated_at": "ISO-8601",
  "ttl_seconds": 10,
  "privacy_mode": "normal",
  "voice": {
    "mode": "mock|push_to_talk|wake_word|disabled",
    "state": "idle|listening_for_wake|wake_detected|recording|transcribing|thinking|searching|needs_clarification|speaking_or_result|error|privacy_blocked",
    "wake_phrase": "hej Pedro",
    "mic_status": "unknown|available|muted|missing|error",
    "stt_status": "not_configured|ready|busy|error",
    "runner_status": "not_configured|ready|busy|error"
  },
  "utterance": {
    "partial": "",
    "final": "",
    "language": "pl",
    "confidence": null
  },
  "activity": {
    "label": "Słucham",
    "detail": "bezpieczny opis bez sekretów",
    "spinner": false
  },
  "result": {
    "summary": "krótki wynik na ekran",
    "requires_user_action": false,
    "clarifying_question": null
  },
  "error": {
    "code": null,
    "message_public": null,
    "debug_ref": null
  }
}
```

---

## Implementation tasks

### Task 0: Host inventory snapshot

**Objective:** Confirm the live iMac constraints before coding.

**Files:**
- Create: `docs/host_inventory.md`

**Steps:**
1. On iMac, record OS, browser path, screen resolution, RAM/swap, Python version, Hermes status, OpenViking status.
2. Do not print secrets.
3. Save findings to `docs/host_inventory.md`.

**Commands to run remotely/local as appropriate:**

```bash
hostname
cat /etc/os-release | sed -n '1,10p'
DISPLAY=:0 xrandr --current | sed -n '1,80p'
command -v google-chrome || command -v chromium || command -v chromium-browser || true
free -h
df -h / /home 2>/dev/null || df -h /
python3 --version
~/.local/bin/hermes status --all | sed -n '1,120p'
```

**Exit:** inventory proves no-systemd path and target resolution.

---

### Task 1: Create minimal project skeleton

**Objective:** Create implementation directories without Node/build tooling.

**Files:**
- Create: `app/server.py`
- Create: `app/static/index.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`
- Create: `app/state/.gitkeep`
- Create: `scripts/.gitkeep`
- Create: `logs/.gitkeep`

**Verification:**

```bash
python3 -m py_compile app/server.py
```

**Exit:** skeleton exists and Python compiles.

---

### Task 2: Implement atomic JSON helper

**Objective:** Add one tiny utility for all state writes.

**Files:**
- Create: `app/state_writer.py`
- Create: `tests/test_state_writer.py`

**Test cases:**
- writes valid JSON;
- overwrites existing state atomically;
- does not leave broken target on simulated bad input;
- includes `updated_at` and `schema_version`.

**Verification:**

```bash
python3 -m pytest tests/test_state_writer.py -q
```

If pytest is not installed yet, use stdlib `unittest` for MVP instead of installing heavy tooling.

---

### Task 3: Build mock state generator

**Objective:** Generate all MVP JSON files, including voice state transitions.

**Files:**
- Create: `scripts/write-mock-state.py`
- Create: `scripts/mock-voice-result.py`

**Required states:**
- dashboard_status;
- system_status;
- hermes_status;
- openviking_status;
- current_focus;
- alerts;
- decisions;
- voice_console.

**Verification:**

```bash
python3 scripts/write-mock-state.py
python3 scripts/mock-voice-result.py "hej Pedro, pokaż dzisiejszy plan"
python3 -m json.tool app/state/voice_console.json >/dev/null
```

**Exit:** LL can be driven entirely by JSON without audio.

---

### Task 4: Serve static UI and API state

**Objective:** Local server returns UI and JSON aggregate.

**Files:**
- Modify: `app/server.py`

**Endpoints:**
- `GET /` static HTML;
- `GET /api/health`;
- `GET /api/state` aggregate;
- `GET /api/voice_console`;
- no secrets, no raw logs.

**Verification:**

```bash
python3 app/server.py --host 127.0.0.1 --port 17890
curl -fsS http://127.0.0.1:17890/api/health
curl -fsS http://127.0.0.1:17890/api/state | python3 -m json.tool >/dev/null
```

**Exit:** server is usable by Chrome kiosk.

---

### Task 5: Build 1920×1200 static cockpit

**Objective:** Render the 2×2 room cockpit from JSON.

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/styles.css`
- Modify: `app/static/app.js`

**Acceptance:**
- no scroll at 1920×1200;
- readable from across a room;
- clear degraded/error/stale states;
- LL has distinct voice states and result area;
- privacy mode visible in header.

**Verification:**
- open Chrome/Chromium at `http://127.0.0.1:17890/`;
- simulate stale/missing `voice_console.json`;
- simulate guest/private mode.

---

### Task 6: Add real lightweight probes

**Objective:** Replace some mocks with safe health probes.

**Files:**
- Create: `scripts/refresh-system-status.py`
- Create: `scripts/refresh-hermes-status.py`
- Create: `scripts/refresh-openviking-status.py`

**Rules:**
- subprocess timeouts 1–3 seconds;
- never expose raw logs;
- sanitize paths/messages;
- output only status, short public message, timestamp.

**Verification:**

```bash
python3 scripts/refresh-system-status.py
python3 scripts/refresh-hermes-status.py
python3 scripts/refresh-openviking-status.py
python3 -m json.tool app/state/system_status.json >/dev/null
```

---

### Task 7: Add no-systemd lifecycle scripts

**Objective:** Make dashboard operable on MX Linux desktop.

**Files:**
- Create: `scripts/start-dashboard.sh`
- Create: `scripts/stop-dashboard.sh`
- Create: `scripts/status-dashboard.sh`
- Create: `scripts/start-kiosk.sh`
- Create: `scripts/watchdog-dashboard.sh`
- Create: `scripts/install-autostart.sh`

**Rules:**
- no systemctl;
- file logs under `~/.local/state/pedro_dashboard/logs/`;
- pid files under `~/.local/state/pedro_dashboard/run/`;
- Chrome profile under `~/.local/share/pedro_dashboard/chrome-profile`;
- bind server to `127.0.0.1`.

**Verification:**

```bash
bash scripts/start-dashboard.sh
bash scripts/status-dashboard.sh
bash scripts/start-kiosk.sh
bash scripts/watchdog-dashboard.sh --once
```

---

### Task 8: Install XDG autostart + crontab fallback

**Objective:** Dashboard returns after login/reboot without systemd.

**Files:**
- Generated by script: `~/.config/autostart/pedro-dashboard.desktop`
- Generated by script: `~/.config/autostart/pedro-dashboard-kiosk.desktop`

**Verification:**
- logout/login test;
- reboot/login test;
- `crontab -l` reviewed before write;
- kill Chrome and server, watchdog restores.

---

### Task 9: Privacy hardening

**Objective:** Ensure room-visible safety.

**Files:**
- Modify: `app/server.py`
- Modify: `app/static/app.js`
- Modify: `scripts/*refresh*.py`

**Tests:**
- `guest` hides transcript/result;
- `private` hides full transcript/private details;
- raw logs never appear;
- secret-looking strings are redacted before state write.

**Exit:** safe to leave on screen with guests.

---

### Task 10: Voice phase B — manual/push-to-talk design only

**Objective:** Prepare the next phase without enabling always-listening.

**Files:**
- Create: `docs/voice_phase_b_design.md`

**Contents:**
- STT provider options: local faster-whisper vs Groq/OpenAI/Mistral;
- CPU/RAM risk;
- how command reaches Hermes runner;
- allowlist and timeout policy;
- privacy policy for transcripts;
- no wake-word until phase C.

**Exit:** clear next step without scope creep.

---

## Acceptance criteria for MVP

- `curl http://127.0.0.1:17890/api/health` returns OK.
- Dashboard loads in Chrome kiosk at 1920×1200 with no scroll.
- LL shows Pedro Voice Console states from `voice_console.json`.
- Missing/corrupt JSON shows degraded state, not white screen.
- `private` and `guest` modes hide sensitive voice result/transcript content.
- Kill server → watchdog restores.
- Kill Chrome → watchdog restores.
- Stop Hermes/OpenViking → dashboard shows offline/degraded, not crash.
- Runs for 1 hour without runaway RAM/swap.
- No systemd dependency exists in MVP scripts.

---

## Out of scope for MVP

- React/Vite/Node build pipeline.
- Electron.
- Always-listening wake phrase.
- Full Polsat/media playback.
- Google OAuth integrations.
- Google Photos slideshow.
- Public LAN exposure.
- Any dashboard button that executes dangerous commands.

---

## Decision log to keep current

Whenever a decision changes, update `PROJECT_DECISIONS.md`:

- port;
- browser binary;
- project path;
- privacy default;
- STT provider;
- wake-word engine;
- whether LAN access is enabled;
- whether React/Electron is allowed after MVP.
