# PROJECT_DECISIONS — Pedro Dashboard

This file is the living decision log for `/pedro_dashboard`.

## Locked decisions

- **Project path:** `/linus1/hermes/projects/pedro_dashboard`.
- **User-facing project name:** `/pedro_dashboard`.
- **Target host:** iMac-Hermes, MX Linux/no-systemd.
- **Target display:** 1920×1200, 16:10.
- **MVP runtime:** local Python server + static HTML/CSS/vanilla JS.
- **MVP browser:** Chrome/Chromium kiosk.
- **MVP deployment:** XDG autostart + shell watchdog + crontab fallback.
- **MVP state:** local JSON files, atomic writes.
- **LL panel:** Pedro Voice Console.
- **Wake phrase:** `hej Pedro` — future phase, not MVP.
- **MVP voice:** mock `voice_console.json` and mock scripts only.
- **Sports widget:** siatkówka reprezentacji Polski; free-first; PZPS/Volleyball World/CEV as official context; TheSportsDB as first structured API candidate.
- **Privacy modes:** `normal`, `private`, `guest`.
- **Default bind:** `127.0.0.1`, no LAN exposure unless explicitly approved.

## Pending decisions before implementation

- Exact port: proposed `17890`.
- Browser binary: `google-chrome` vs `chromium` on iMac.
- Default privacy mode: proposed `private` if guests/family may see the screen; `normal` if strictly private room.
- State directory in production: proposed `~/.local/state/pedro_dashboard/state/`.
- Log directory: proposed `~/.local/state/pedro_dashboard/logs/`.
- Whether dashboard repo stays plan-only until Codex starts implementation, or code is added here directly.
- Whether Jurand means **Groq** API for Whisper STT or **xAI/Grok** API for STT/TTS; both are cloud options, neither is MVP-critical.

## Future decisions — not MVP

- STT provider: local faster-whisper vs Groq/OpenAI/Mistral.
- TTS provider: xAI/Grok vs Edge/OpenAI/Mistral/other.
- Wake-word engine for Polish `hej Pedro`.
- Whether TTS speaks answers aloud.
- Whether LAN access is allowed.
- Whether React/Vite is worth adding after stable MVP.
- Whether Electron is ever needed for media/Polsat use cases.
