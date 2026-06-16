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
- **Wake phrase:** `hej Pedro` — future phase, not MVP. **Update v1.2:** user-facing wake phrase is `hey pedro` (case-insensitive, `hej pedro` / `pedro` accepted as variants). Technical trigger is **push-to-talk (hold Space)**; the phrase "hey pedro" is a prefix gate on the Gemini STT transcript, not an audio-side KWS. v1.3+ may add a true always-listening KWS via Vosk on this CPU.
- **MVP voice:** mock `voice_console.json` and mock scripts only.
- **MVP voice v1.2:** push-to-talk daemon (`scripts/pedro_voice_daemon.py`) → ALSA capture → Gemini multimodal STT (`scripts/pedro-voice-stt.py`, model `gemini-2.5-flash` with `gemini-flash-latest` fallback) → "hey pedro" prefix gate → static allowlist runner (`scripts/pedro-runner.py` + `scripts/pedro_runner_allowlist.json`) → local espeak-ng TTS (`scripts/pedro-voice-tts.py`, voice `pl`).
- **Voice venv:** `~/.local/share/pedro-voice-venv` with `python-xlib` only. The voice venv deliberately does NOT include `onnxruntime` / `tflite-runtime` / `openwakeword` because the iMac-Hermes CPU (Core 2 Duo T7700, flags `sse sse2 ssse3` only, no SSE4.1/AVX/AVX2) crashes those libraries with SIGILL on import.
- **Trigger key:** `Space` (X11 keycode 65) by default. Override via `PEDRO_VOICE_TRIGGER_KEYCODE`. The daemon polls the X11 keyboard state via `python-xlib`; it does not `XGrabKey`, so the keystroke still reaches Chrome.
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

- True always-listening "hey pedro" wake-word (v1.3+). Blocked on this CPU (no SSE4.1+) and RAM budget. Candidate: Vosk small PL ASR + energy VAD + keyword gate (~80-120 MiB idle, ~5-15% CPU on Core 2).
- TTS provider: xAI/Grok vs Edge/OpenAI/Mistral/other.
- Whether LAN access is allowed.
- Whether React/Vite is worth adding after stable MVP.
- Whether Electron is ever needed for media/Polsat use cases.
