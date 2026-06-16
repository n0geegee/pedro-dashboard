# Host inventory — Pedro Dashboard

Generated: 2026-06-15T13:33:11+02:00  
Host: `imac-hermes`  
Project root used on this host: `/home/imac-hermes/projects/pedro_dashboard`

> Safety: this file records public operational facts only. No secrets, tokens, raw private messages, or credential paths were collected.

## Summary

- Host is ready for the lightweight MVP path: Python + static files + JSON state + Chrome kiosk.
- Target display is present at `DISPLAY=:0`: `1920x1200` on `LVDS`.
- Chrome is available; Chromium is not required for MVP on this host.
- Planned dashboard port `17890` is currently free.
- Hermes gateway and OpenViking are running; OpenViking `/health` is OK.
- Project is currently plan-only plus this inventory artifact; no app/runtime files exist yet.
- Directory is not currently a git repository.

## OS / no-systemd posture

Live command source: `uname -a`, `/etc/os-release`.

```text
Linux imac-hermes 6.12.63+deb13-amd64 #1 SMP PREEMPT_DYNAMIC Debian 6.12.63-1 (2025-12-30) x86_64 GNU/Linux
PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
VERSION_ID="13"
VERSION="13 (trixie)"
```

Project docs say MX Linux/no-systemd. Live host presents as Debian 13. MVP must still follow the locked no-systemd rule: no required `systemctl`, systemd timers, or `journalctl` path. Use XDG autostart, shell scripts, cron/watchdog, and file logs.

## Display / kiosk target

Live command source: `DISPLAY=:0 xrandr --current`.

```text
Screen 0: current 1920 x 1200
LVDS connected 1920x1200+0+0
1920x1200 60.24*+
```

Note: the Hermes/Discord worker shell had empty `$DISPLAY`, but `DISPLAY=:0` works. Kiosk scripts should explicitly handle desktop-session environment and use `DISPLAY=:0` as fallback when appropriate.

## Browser

Live command source: `command -v` scan.

```text
google-chrome: /usr/bin/google-chrome
google-chrome-stable: /usr/bin/google-chrome-stable
chromium: not found
chromium-browser: not found
```

MVP browser choice on this host: `google-chrome`.

## Runtime/tooling

Live command source: `command -v`, version commands.

```text
python3: /usr/bin/python3
Python: 3.13.5

git: /usr/bin/git
git version: 2.47.3

codex: /home/imac-hermes/.local/bin/codex
codex-cli: 0.139.0

clawpatch: /home/imac-hermes/.local/bin/clawpatch
clawpatch version output: 0.1.0

hermes: /home/imac-hermes/.local/bin/hermes
Hermes Agent: v0.16.0 (2026.6.5)
```

MVP should prefer Python stdlib first. No Node/React/Electron as MVP dependency.

## Memory / disk

Live command source: `free -h`, `df -h . ~`.

```text
RAM total: 5.8 GiB
RAM available during inventory: 4.3 GiB
Swap total: 2.0 GiB
Swap used during inventory: 347 MiB

Root/home filesystem: /dev/sda2
Size: 1.8T
Used: 23G
Available: 1.7T
Use: 2%
```

Resource note: enough for lightweight server + Chrome kiosk. Avoid always-on local STT/LLM/Node watchers in MVP.

## Ports / local services

Live command source: `ss -ltnp` filtered to relevant ports.

```text
127.0.0.1:1933  listening  OpenViking server
0.0.0.0:40219   listening  gateway-related UI/service
127.0.0.1:17890 not listening / free
```

Dashboard default can use `127.0.0.1:17890`.

## Hermes gateway status

Live command source: `/home/imac-hermes/hermes-gateway-watchdog.sh status`.

```text
watchdog daemon running
gateway process running: hermes gateway run
logs exist under ~/.hermes/logs/
```

UI rule: dashboard may show public status only, never raw logs or prompt/session text.

## OpenViking health

Live command source: `curl -fsS --max-time 3 http://127.0.0.1:1933/health`.

```json
{"status":"ok","healthy":true,"version":"0.3.14","auth_mode":"dev"}
```

UI rule: show health/availability only unless a future explicit command and privacy mode allow content lookup.

## Project directory state

Live source: file listing under `/home/imac-hermes/projects/pedro_dashboard`.

Existing plan files:

```text
00_prompt_dla_pedro_start_HERE.md
00_MASTER_PLAN.md
01_product_outline.md
02_mvp_architecture.md
03_voice_console_contract.md
04_mx_linux_ops_plan.md
05_privacy_modes.md
06_delivery_roadmap.md
07_blocking_risks.md
08_CODEX_PROMPTS.md
09_QA_ACCEPTANCE.md
10_APIS_AND_TOOLS.md
11_FREE_FIRST_VOLLEYBALL_AND_VOICE_GUIDANCE.md
12_IMAC_HERMES_ORCHESTRATOR_PROMPT.md
PLAN_FILES_SUMMARY.md
PROJECT_DECISIONS.md
README.md
```

Implementation gaps before MVP:

```text
app/server.py
app/static/index.html
app/static/styles.css
app/static/app.js
app/state/*.json
scripts/write-mock-state.py
scripts/mock-voice-result.py
scripts/start-dashboard.sh
scripts/stop-dashboard.sh
scripts/status-dashboard.sh
scripts/start-kiosk.sh
scripts/watchdog-dashboard.sh
scripts/install-autostart.sh
```

Git status:

```text
not a git repository
```

## First safe next step

Proceed with Prompt 1 / Etap 1:

1. Create the minimal Python/static skeleton in this local project root.
2. Bind server to `127.0.0.1:17890`.
3. Add mock JSON state files and Pedro Voice Console contract.
4. Verify with:
   - `python3 -m py_compile app/server.py`
   - `python3 scripts/write-mock-state.py`
   - `curl -fsS http://127.0.0.1:17890/api/health`
   - JSON validation via `python3 -m json.tool`

Do not start sports, Google Maps, or real voice/audio before the cockpit skeleton works.
