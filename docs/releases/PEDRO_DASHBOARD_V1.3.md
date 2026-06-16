# Pedro Dashboard v1.3 — voice "hey pedro" (push-to-talk)

Release timestamp: 2026-06-16T12:30:00Z

## Milestone meaning

This release wires the **LL Pedro Voice Console** to a real audio +
STT + TTS pipeline. The user-facing wake phrase is **"hey pedro"**;
the technical trigger is **push-to-talk** (hold the `Space` key). The
kiosk stays passive: no on-screen button, no click handler, the user
presses a physical key.

This is **not** a true always-listening wake-word. The iMac-Hermes
CPU (Core 2 Duo T7700, flags `sse sse2 ssse3` only, no
SSE4.1/AVX/AVX2) crashes `onnxruntime` and `tflite-runtime` with
SIGILL on import, so `openwakeword` and similar libraries are
**not viable** on this hardware. A true always-listening KWS is
deferred to v1.4+ (candidate: Vosk small PL ASR + energy VAD).

## Architecture (one paragraph)

A long-lived `pedro_voice_daemon.py` polls the X11 keyboard state at
20 Hz via `python-xlib` and watches keycode 65 (Space). On press, the
daemon writes `voice_console.json` state `wake_detected` and starts a
4 s ALSA capture via `arecord` (HDA Intel ALC889A, device
`plughw:0,0`, 16 kHz mono 16-bit). On release, the WAV is sent to
Google Gemini (`gemini-2.5-flash` with `gemini-flash-latest` fallback)
for Polish transcription. The transcript is locally gated against the
prefixes `hey pedro`, `hej pedro`, `pedro`; on match, the rest is
dispatched to a static allowlist runner (`pedro-runner.py`) that reads
the relevant `app/state/*.json` file and writes a short Polish
summary. The summary is spoken via local `espeak-ng` (voice `pl`,
rate 165). The full state machine is documented in
`docs/voice_phase_b_design.md`.

## Files added

### Voice venv

- `~/.local/share/pedro-voice-venv` — dedicated Python venv with
  `python-xlib`, `requests`, `urllib3`, `certifi`, `numpy`, `scipy`,
  `vosk` (kept for v1.4 work). Deliberately does **not** include
  `onnxruntime`, `tflite-runtime`, or `openwakeword` (SIGILL on
  this CPU).

### Voice scripts (in `scripts/`)

- `pedro_voice_daemon.py` — long-lived push-to-talk controller.
  Polls X11 keyboard state, drives the state machine, never grabs
  the key, never blocks the kiosk. PID file:
  `~/.local/state/pedro_dashboard/run/voice_daemon.pid`. Log:
  `~/.local/state/pedro_dashboard/logs/voice_daemon.log`.
- `pedro-voice-record.py` — ALSA capture helper, 16 kHz mono 16-bit
  WAV, RMS gate to detect silence, exit code 0/2 (silence)/3+
  (errors).
- `pedro-voice-stt.py` — Gemini multimodal audio STT. Stdlib only
  (urllib, base64, json). Models: `gemini-2.5-flash` primary,
  `gemini-flash-latest` fallback. 8 s timeout.
- `pedro-voice-tts.py` — `espeak-ng` wrapper with secret redaction
  and 400-char length cap. Honour `PEDRO_VOICE_SPEAK=off`.
- `pedro-runner.py` — static allowlist router. Reads
  `voice_console.json`, matches `utterance.final` against
  `pedro_runner_allowlist.json`, writes the result back. 5 s
  wall-clock timeout via SIGALRM.
- `pedro_runner_allowlist.json` — 11 intents: `status`, `time`,
  `weather`, `route`, `volleyball`, `focus`, `help`, `replay`,
  `privacy_private`, `privacy_normal`, `privacy_guest`.
- `refresh-voice-console.py` — idle heartbeat driver. If the daemon
  is dead, it repaints `listening_for_wake` so the kiosk does not
  show stale data.
- `start-voice-daemon.sh` / `stop-voice-daemon.sh` /
  `status-voice-daemon.sh` — no-systemd lifecycle helpers, sourced
  from `_lifecycle_common.sh`.

### Documentation

- `docs/voice_phase_b_design.md` — full design doc (host reality,
  options, decision, state machine, failure modes, files).

## Files modified

- `scripts/_lifecycle_common.sh` — added `PEDRO_VOICE_*` path
  conventions and `pedro_voice_daemon_alive()` helper.
- `scripts/refresh-all-state.sh` — added `refresh-voice-console.py`
  to the live probe loop.
- `scripts/watchdog-dashboard.sh` — voice daemon health check +
  restart, gated on `pedro_display_works()` (X must be up for X11
  polling to work).
- `scripts/install-autostart.sh` — added
  `pedro-voice-daemon.desktop` (XDG autostart) and
  `@reboot start-voice-daemon.sh` to the proposed crontab.
- `PROJECT_DECISIONS.md` — recorded v1.2 STT/TTS provider, voice
  venv, and trigger key decisions.
- `PEDRO_INTEGRATION_STATUS.md` — moved `voice_console.json` from
  "contract exists" to "live via push-to-talk daemon".

## How to use

```bash
# Start the daemon (long-lived; autostart does this at login too)
cd /home/imac-hermes/projects/pedro_dashboard
bash scripts/start-voice-daemon.sh

# Status / stop
bash scripts/status-voice-daemon.sh
bash scripts/stop-voice-daemon.sh

# Then in the kiosk: hold Space, say e.g. "hey pedro, jaka jest pogoda",
# release. The kiosk LL card shows the answer; the room hears it via
# espeak-ng.
```

Trigger key override (e.g. right Ctrl):

```bash
PEDRO_VOICE_TRIGGER_KEYCODE=105 bash scripts/start-voice-daemon.sh
```

Microphone device override:

```bash
PEDRO_MIC_DEVICE=plughw:0,2 bash scripts/start-voice-daemon.sh
```

Silent mode (no TTS in the room, results still on screen):

```bash
PEDRO_VOICE_SPEAK=off bash scripts/start-voice-daemon.sh
```

## Verification snapshot

- `python3 -m py_compile` on all 6 voice scripts → OK.
- `bash -n` on all 4 voice shell scripts and modified lifecycle
  scripts → OK.
- ALSA capture roundtrip: `arecord -D plughw:0,0 -d 2 -f S16_LE
  -r 16000 -c 1` → 64 KiB WAV, RMS computed, silence correctly
  detected (exit 2 from `pedro-voice-record.py`).
- Gemini STT roundtrip on a silence WAV → returned a hallucination
  ("włącz światło"); runner correctly rejected it as
  `INTENT_NOT_ALLOWED`. A real utterance ("hey pedro, status")
  must be tested by a human.
- Runner dry-run + real run on injected state:
  - `status` intent → "Dashboard działa. Wolne RAM 2600 MiB, PID
    489101." (rc=0).
  - `tryb prywatny` intent → "Tryb prywatny włączony.", privacy
    file written.
  - `zrób mi kanapkę` (unknown) → `INTENT_NOT_ALLOWED`, Polish
    "Nie rozpoznano komendy" message.
- `refresh-voice-console.py` with dead daemon repaints
  `listening_for_wake`.
- Daemon `--once` test: connects to X :0, paints idle, exits
  cleanly, removes pid file.
- Full `refresh-all-state.sh` runs in 5 s, rc=0, server still
  healthy (uptime 55005 s).
- 4 XDG autostart entries installed in
  `~/.config/autostart/pedro-*.desktop` (server, refresher, kiosk,
  voice).
- Voice daemon sub-millisecond idle CPU, ~5% during 4 s capture.

## Honest blockers / known limitations

1. **Not a true wake-word.** The user must hold a key. This is the
   only viable approach on this CPU. A real always-listening
   "hey pedro" requires new hardware OR a Vosk-based ASR daemon
   (v1.4+).
2. **Gemini audio halucinates on silence.** Captures below the RMS
   threshold are rejected before STT, but very short utterances
   at the RMS edge may still send a silence-ish WAV and get a
   nonsense transcript. The runner rejects unknown intents
   gracefully, so the worst case is a Polish "Nie rozpoznano
   komendy" message.
3. **No echo cancel.** If the TTS speakers are loud and the mic
   is the same HDA device, espeak-ng may bleed into the next
   capture. The 1.5 s cooldown helps. Real fix is a USB headset
   (out of scope for v1.3).
4. **PulseAudio is dead on this host** (confirmed: `pactl info`
   returns "Connection refused"). The voice path uses ALSA
   directly via `arecord` and `espeak-ng` ALSA sink, which works
   without PA. If PA is ever revived, audio routing may need to
   be revisited.
5. **Kiosk server may not be running on the iMac 24/7.** The
   watchdog restarts the voice daemon when DISPLAY is up. If
   X is dead, the daemon stays dead. The user-facing instruction
   on the LL card is to press Space when the dashboard is visible.
6. **`/api/voice_console` returns the same JSON that the daemon
   writes.** No code change in `app/server.py` was required. The
   contract is unchanged from v1.1.

## v1.3 rules going forward

- Treat v1.3 as the **accepted voice baseline**. UI hints about
  "press Space" or "powiedz 'hey pedro'" must come from the JSON
  contract, not from hardcoded text in `index.html`.
- `voice_console.json` is owned by the daemon when the daemon is
  alive. `refresh-voice-console.py` only repaints when the daemon
  is dead, or when a previous daemon left a stuck error state.
- Adding a new intent is a code change to
  `pedro_runner_allowlist.json` + review. There is no runtime
  API to add intents.
- Voice venv at `~/.local/share/pedro-voice-venv` must stay
  minimal. Do not install `onnxruntime` or `tflite-runtime` on
  this host — they will SIGILL.
- If a future operator wants a different trigger key, override
  `PEDRO_VOICE_TRIGGER_KEYCODE` in the autostart `.desktop` file.
  Do not change the default.
