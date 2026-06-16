# Pedro Voice — Phase B design (push-to-talk, "hey pedro" gating)

> **Status:** design lock for v1.2 (post-v1.1 polish). Implements Faza 4
> from `06_delivery_roadmap.md` and Task 10 from `00_MASTER_PLAN.md`.
> Jurand directive: voice is activated by the phrase "hey pedro".
> **Reality of iMac CPU** (Core 2 Duo T7700, 2007-era, flags
> `sse sse2 ssse3` only, no SSE4.1/AVX/AVX2) means dedicated
> always-listening KWS engines (openwakeword / onnxruntime /
> tflite-runtime ≥ 2.x) **crash with SIGILL on import**. So v1.2 ships
> **push-to-talk (a key the user holds) + Gemini STT for the command
> after "hey pedro"** instead. The phrase "hey pedro" remains the
> user-facing wake phrase; the technical detection is the keypress.
> Always-listening KWS is a v1.3+ item requiring new hardware or a
> Vosk-based custom keyword spotter running on this CPU.
> **Audience:** Jurand + future Codex/Hermes review.
> **Goal:** wire real audio → STT → Hermes runner → TTS in a way that
> is safe, bounded, observable, and survives 1+ hour on the old iMac.

## 1. Host reality (grounded in current iMac)

Captured 2026-06-16, iMac-Hermes, MX Linux 13 (trixie), kernel 6.12.

| Probe | Value | Implication |
|---|---|---|
| `free -h` | 5.8 GiB total, **577 MiB available**, 2.0 GiB swap (361 MiB used) | cannot preload 400-800 MiB ML model without swap thrash |
| `lscpu` (best effort) | Intel Core2-class iMac, no AVX2 in some revisions | disqualifies heavy local ASR |
| `arecord -l` | card 0: HDA Intel ALC889A, devices 0/1/2 visible | ALSA capture works directly |
| `pactl info` | `Connection refused` | **PulseAudio / PipeWire is dead on this host** — any lib using `sounddevice`/`pyaudio`/Pulse will fail |
| Audio tools | `arecord`, `parec` (unused without PA), `ffmpeg`, `sox`, `espeak-ng` all present | full ALSA + postproc + local TTS path is available |
| Python pkgs (system) | `faster_whisper` ✗, `openai-whisper` ✗, `sounddevice` ✗ | no Python ASR installed; hermes-agent venv also lacks them |
| Hermes keys | `MiniMax` ✓, `Google / Gemini` ✓, OpenAI ✗, Groq ✗ | cloud STT candidates: Gemini only (local LLM key, no quota proof) |
| `~/.cache/huggingface/` | empty | cold-start of any local Whisper is multi-second and full of model download |
| Dashboard | running on `127.0.0.1:17888`, `api/health` returns ok | voice_console.json is already consumed by UI |
| `voice_console.json` | currently `mode=mock`, `stt_status=not_configured`, `runner_status=not_configured` | clean slate to attach a real driver |

## 2. Options considered

| # | Option | RAM cost | CPU idle | Privacy | Failure mode | Verdict |
|---|---|---|---|---|---|---|
| A | **`openwakeword` `hey_jarvis` always-listening** | ~120-180 MiB (onnxruntime + 1 model) | 1-3% on Core2 | audio leaves host only after wake trigger | **onnxruntime 1.15+ crashes with SIGILL on Core 2 T7700 (no SSE4.1/AVX)** | **rejected (CPU)** |
| B | Custom-trained "hey pedro" model in openwakeword | same as A | same as A | same as A | inherits A's failure | rejected (inherits A) |
| C | **Push-to-talk (hold key) + Gemini STT + "hey pedro" prefix gate** | ~30-40 MiB (idle: 0) | 0 idle, ~5% during 4 s capture | audio leaves host only on press | key never pressed (UX) | **chosen for v1.2** |
| D | Porcupine (Picovoice) custom keyword | ~50-80 MiB | <1% (binary) | same as A | commercial key, free tier limits | rejected (new paid key + needs custom "hey pedro" training) |
| E | Always-listening Vosk ASR + custom keyword gate | ~80-120 MiB (Vosk + model) | 5-15% on Core2 | audio stays on host | high idle CPU on this CPU | deferred to v1.3+ (CPU/RAM budget) |
| F | Whisper.cpp + KWS-free energy trigger | ~250 MiB peak | medium | audio leaves host on trigger | cold start; CPU already at edge | rejected (CPU/RAM) |

**Decision lock for v1.2:** **C — Push-to-talk (hold Space or a physical
key) → 4 s ALSA capture → Gemini STT → "hey pedro" prefix gate → Hermes
runner → espeak-ng TTS.** The user holds a key while saying the
command; the command must start with the Polish wake phrase
"hey pedro" (or "hej pedro" / "pedro" — case-insensitive, all variants
accepted). The kiosk shows "Przytrzymaj klawisz i powiedz 'hey pedro,
<komenda>'" as the idle hint.

The key itself is a **physical key** so the user does not need a
clickable button (kiosk is still passive). Defaults:

- **Space** as primary trigger (every USB keyboard has it)
- `Right Ctrl` as alternate (for split keyboards)
- Configurable via `PEDRO_VOICE_TRIGGER_KEY` env var

The key listener is `pedro_voice_daemon.py` running as a long-lived
background process; it uses `python-xlib` (pure-Python X11 bindings,
no onnx/tflite) to read key state without intercepting input. Tested
on MX Linux XFCE.

**Why "hey pedro" is a prefix gate, not a wake-word:**
- A real wake-word is what the audio detection hears. We do not have
  audio-side detection in v1.2.
- A prefix gate is what the STT transcript must start with. We
  *do* have STT.
- Together they give the same UX: the user says "hey pedro, ..." and
  only that triggers a result. Random speech, other people talking
  in the room, TV noise — none of it produces a STT call because the
  key is not pressed.

### 2.1 Why not Hermes `text_to_speech` tool

The Hermes `text_to_speech` tool goes through a provider that is configured
provider-side, not at the agent level. For the kiosk we need deterministic
behaviour: the same voice, the same latency budget, the same binary, no
`text_to_speech` provider outage taking the room silent. `espeak-ng` is
already installed, ~5 MiB, deterministic, and Polish voices exist
(`pl`, `pl+en`). We use `espeak-ng` for TTS.

### 2.2 Why not Groq Whisper / OpenAI Whisper

Neither key is configured on this host. Adding a paid key for one subsystem
when Gemini key is already authorised and supports audio multimodal is scope
creep and a new billing surface.

## 3. Trigger model — push-to-talk with "hey pedro" prefix

- Trigger: **hold a physical key** (default `Space`) and speak.
  Releasing the key stops the capture. The kiosk is still passive;
  no on-screen button.
- The key listener is `pedro_voice_daemon.py` running as a long-lived
  background process. It uses `python-xlib` (no onnx/tflite) to
  query X server key state. It does **not** `XGrabKey` (that would
  eat the keystroke from the kiosk); it only polls the keyboard
  state at ~20 Hz.
- The daemon owns `voice_console.json` in `wake_word` mode (we keep
  the field name for contract stability) and writes:
  - `listening_for_wake` when the daemon is alive and the key is
    not pressed;
  - `wake_detected` the moment the key transitions to pressed;
  - `recording` while the key is held (capped at 5 s);
  - `transcribing` while Gemini STT runs (≤8 s);
  - `thinking` while the runner runs (≤5 s);
  - `speaking_or_result` after TTS starts;
  - back to `listening_for_wake` after a 1.5 s cooldown.
- Microphone capture device: `plughw:0,0`. If ALSA returns no device,
  the daemon falls back to `plughw:0,2` (HDA Intel ALC889A Alt
  Analog), then to `default`. If all three fail, the daemon exits
  with `error.code=AUDIO_CAPTURE_FAILED` and the watchdog
  (`scripts/watchdog-dashboard.sh`) restarts it after 30 s with
  backoff. We do **not** busy-loop.
- "hey pedro" prefix check: the STT transcript must start (after
  lowercasing and stripping punctuation) with one of:
  - `hey pedro`
  - `hej pedro`
  - `pedro`
  If not, the event is rejected as `WAKE_PHRASE_NOT_DETECTED`. The
  kiosk shows "Nie usłyszałem 'hey pedro'." and espeak-ng says
  "Powiedz hey pedro przed komendą."

## 4. Audio capture

- Use **ALSA directly** via `arecord`. PulseAudio is dead on this host;
  `parec` will fail. We do not fix PulseAudio in this phase.
- Default device: `plughw:0,0` (HDA Intel ALC889A Analog, subdevice 0).
  Captured 16-bit mono PCM, 16 kHz, ~3 s per utterance.
- `arecord -D plughw:0,0 -d 3 -f S16_LE -r 16000 -c 1 /tmp/pedro-ptt.wav`
  as the canonical capture.
- Push-to-talk timeout: 5 s hard limit. If `arecord` exits 0 in <3 s (user
  released key early), we still send what we have.
- If capture fails (device busy, no mic, ALSA error), we mark
  `mic_status=error`, write `error.code=AUDIO_CAPTURE_FAILED`, and **do
  not** keep retrying in a tight loop. The user re-issues the trigger.

## 5. STT — Gemini multimodal audio

- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`
  (fallback documented: `gemini-1.5-flash` if 2.0 returns 404).
- Auth: API key from `~/.hermes/.env` (`GOOGLE_API_KEY` or `GEMINI_API_KEY`).
  Loaded by `refresh-all-state.sh` via `set -a; source ...`. Not printed.
- Request: inline base64 audio with `mime_type: audio/wav`. Prompt:
  ```
  This audio starts with the Polish wake phrase "hey pedro" and then
  contains a short Polish voice command. Transcribe ONLY the part AFTER
  the wake phrase (i.e. the command itself). Output the literal Polish
  transcription, no quotes, no commentary, no leading "pedro" / "pedro".
  If you cannot hear any command after the wake phrase, output the
  single word: <UNK>.
  ```
- `temperature=0`, `maxOutputTokens=128`.
- Timeout: 8 s. Treat any 4xx/5xx/timeout as `stt_status=error`,
  `error.code=STT_UPSTREAM_ERROR`. We do **not** retry automatically —
  the user re-issues "hey pedro".
- The Gemini response is parsed for the first non-empty text part. If the
  text equals `<UNK>` or is empty after stripping, set
  `utterance.final=""`, `activity.label="Nie rozumiem"`, finish in
  `speaking_or_result` with no clarifying question.
- Confidence is not provided by Gemini multimodal reliably. We set
  `utterance.confidence=null` and do not pretend a number. UI must handle
  null gracefully (already does in v1.1).

### 5.3 "hey pedro" prefix gate (Gemini transcript only)

Because the technical trigger is the keypress and the user-facing
phrase is "hey pedro", we run a cheap prefix check on the Gemini
transcript before going to the runner:

1. After the key is released (capture done), the 4 s WAV is sent to
   Gemini (§5).
2. The first 80 characters of the transcript are normalised
   (lowercased, stripped of punctuation and leading whitespace).
3. The daemon checks if the normalised text starts with one of:
   `hey pedro`, `hej pedro`, `pedro`.
4. If NO, the event is rejected. UI shows "Nie usłyszałem 'hey pedro'."
   TTS says "Powiedz hey pedro przed komendą." Daemon returns to
   `listening_for_wake` after 1.5 s.
5. If YES, the wake phrase is stripped from the transcript and the
   remaining text is the actual command. Daemon goes to
   `thinking` → runner.

This gate is local (no extra Gemini call). Latency cost: ~1 ms.

## 6. Hermes runner — bounded command dispatch

We **do not** call the Hermes gateway directly from the voice script in v1.2.
The voice driver only does audio → STT → write `voice_console.json`. The
*runner* is a separate script: `scripts/pedro-runner.py`.

- The runner consumes the final `voice_console.json` (state
  `speaking_or_result` with `utterance.final` set).
- It matches the final text against a static **allowlist of intents**
  in `scripts/pedro_runner_allowlist.json`. Unknown intents write
  `error.code=INTENT_NOT_ALLOWED` and a public
  "Nie rozpoznano komendy" message.
- Allowlist v1.2 covers:
  - `status` → return one-line current system status (RAM, dashboard pid).
  - `time` → current Europe/Warsaw time.
  - `weather` → cached weather card summary (read existing
    `weather.json`; do not refetch).
  - `route` → cached route summary (read `route.json`).
  - `volleyball` → next PL match from `volleyball.json`.
  - `focus` → first item of `current_focus.json` data list.
  - `private_on` / `private_off` / `guest_on` / `normal_on` → set
    `DASHBOARD_PRIVACY_MODE` via `~/.config/pedro-dashboard/privacy_mode`
    and trigger `refresh-voice-console.py --apply-privacy` to repaint.
  - `replay` → re-speak last summary via TTS.
  - `help` → list of allowed intents.
- Hard timeout: **5 s per runner call**. Wall-clock budget end-to-end
  (capture → STT → runner → TTS): **20 s**.
- All runner work runs in a **child process** so a runaway TTS or
  gateway call cannot wedge the dashboard server. PID is recorded in
  `~/.local/state/pedro_dashboard/run/voice_runner.pid`.

### 6.1 Why a static allowlist, not the LLM

The runner is a *command router*, not a free-form agent. A free-form
agent in a kiosk with always-room visibility is a privacy and safety
disaster. Static allowlist in v1.2 means: any unanticipated intent is
denied by default. Adding a new intent is a code change, not a runtime
decision. Jurand reviews the allowlist.

## 7. TTS — local espeak-ng

- Binary: `/usr/bin/espeak-ng`. Voices: `pl` (Polish) is default. We do
  not download cloud voices.
- Invocation: `espeak-ng -v pl -s 165 -p 50 "<sanitised summary>"`
  - `-s 165` rate (room-friendly; default 175 is slightly fast)
  - `-p 50` pitch (slightly deeper, more "Pedro" than robot)
- Output: ALSA default sink. We do not write to a file by default; if
  `PEDRO_VOICE_SPEAK=off` is set, TTS is skipped (silent kiosk mode).
- Sanitisation: same `_redact_public_text` regex family used by
  `mock-voice-result.py`. Length cap 400 chars; longer summaries are
  truncated with "...".
- Failure mode: if `espeak-ng` is missing or exits non-zero, write
  `runner_status=error`, `error.code=TTS_FAILED`, and the dashboard
  card shows the text result anyway. The room is not silent because of
  a TTS crash.

## 8. State machine

`voice_console.json` state transitions, exactly as in
`03_voice_console_contract.md`:

```
idle
  └─ Ctrl+Alt+P / CLI trigger
       └─ recording      (arecord, ≤3 s)
            └─ transcribing   (Gemini STT, ≤8 s)
                 ├─ STT error → error → (back to idle after 5 s)
                 ├─ <UNK> / empty → speaking_or_result (Nie rozumiem) → idle
                 └─ ok → thinking
                      └─ runner (≤5 s)
                           ├─ not_allowed → error → idle
                           ├─ ok → searching? (only if runner does lookup) → speaking_or_result → TTS → idle
                           └─ timeout → error → idle
```

The voice script is a state machine driver; the JSON file is the
single source of truth. The dashboard reads it, the runner reads it.
No shared in-memory state between processes.

## 9. Privacy

- `privacy_mode=normal` → transcript and result shown in UI.
- `privacy_mode=private` → only first 18 chars + "..." of transcript
  shown; full result summary still shown (it's already short).
- `privacy_mode=guest` → transcript hidden, result hidden, panel shows
  "Pedro dostępny" only.
- Audio itself is **never** written to `voice_console.json` and **never**
  logged. WAV files live in `~/.local/state/pedro_dashboard/cache/audio/`
  with 0600 perms and are deleted at script exit (success or fail).
- Gemini request payload: only the audio bytes + the short prompt. No
  PID, no username, no path. We rely on Gemini's normal data policy
  (no `systemInstruction`, no tool calls, no file uploads).
- `voice_console.json` `error.debug_ref` is a **monotonic counter** in
  `~/.local/state/pedro_dashboard/run/voice_debug_counter`, not a
  network error or path. Operators correlate via the lifecycle log.

## 10. Durability on this host

- Capture script is one bash + python, no long-lived daemon in v1.2.
  Each push-to-talk is a fresh process. No memory leak to track.
- The runner is invoked on demand, child process, hard timeout 5 s.
- `refresh-voice-console.py` is also invoked by `state-refresher.sh`
  every ~20 s, but only to **read** the JSON and bump `updated_at`
  if state is `idle`. It never invents activity.
- If `voice_console.json` is missing or stale (>30 s) while voice mode
  is `push_to_talk`, the UI must already render `stale` thanks to
  v1.1 contracts — we do not change that.

## 11. Failure modes summary (for QA)

| Failure | Detected by | UI state | Recovery |
|---|---|---|---|
| Mic busy / no device | `arecord` non-zero | `error`, `mic_status=missing` | operator re-issues |
| Mic muted in hardware | silence in WAV, RMS < threshold | `error`, `mic_status=muted` | operator unmutes |
| Gemini 4xx | HTTP code | `error`, `stt_status=error` | no auto-retry |
| Gemini 5xx | HTTP code | `error`, `stt_status=error` | no auto-retry |
| Gemini timeout | curl timeout 8 s | `error`, `stt_status=error` | no auto-retry |
| Runner intent not allowed | allowlist miss | `error`, `INTENT_NOT_ALLOWED` | none |
| Runner timeout | SIGTERM after 5 s | `error`, `RUNNER_TIMEOUT` | none |
| espeak-ng missing | which / first run | `runner_status=error`, result still shown | install espeak-ng |
| espeak-ng segfault | non-zero exit | `runner_status=error`, result still shown | re-run |

## 12. Files this phase creates / modifies

New:

- `scripts/pedro_voice_daemon.py` — long-lived push-to-talk daemon:
  polls key state via `python-xlib` (pure Python, no onnx), captures
  audio on press, drives the state machine, runs STT + runner + TTS
  in sequence. PID file at
  `~/.local/state/pedro_dashboard/run/voice_daemon.pid`.
- `scripts/pedro-voice-record.py` — ALSA capture helper (≤5 s WAV).
- `scripts/pedro-voice-stt.py` — Gemini audio STT, returns text.
- `scripts/pedro-voice-tts.py` — espeak-ng wrapper, sanitised.
- `scripts/pedro-runner.py` — allowlist router, writes back to JSON.
- `scripts/pedro_runner_allowlist.json` — static intent list.
- `scripts/refresh-voice-console.py` — refresh driver, idle heartbeat.
- `scripts/pedro-voice-test.sh` — test harness: synthesise or play
  a 4 s "hey pedro pokaż status" clip and verify state transitions
  end-to-end without real speech.
- `docs/voice_phase_b_design.md` — this file.

Modified:

- `scripts/refresh-all-state.sh` — add `refresh-voice-console.py` to the loop.
- `scripts/_lifecycle_common.sh` — add `PEDRO_VOICE_*` path conventions
  and `pedro_voice_daemon_alive()` helper.
- `scripts/install-autostart.sh` — autostart entry for the voice daemon.
- `scripts/watchdog-dashboard.sh` — restart voice daemon if dead.
- `app/server.py` — `/api/voice_console` already returns it, no code
  change needed; verify contract still matches.
- `PROJECT_DECISIONS.md` — record STT/TTS provider decision and the
  push-to-talk + "hey pedro" prefix gate.
- `PEDRO_INTEGRATION_STATUS.md` — move `voice_console.json` from
  "contract exists, not connected" to "live via push-to-talk daemon".

## 13. Out of scope (deferred)

- True always-listening "hey pedro" wake-word (v1.3+). Blocked on
  this CPU (no SSE4.1+ for onnxruntime/tflite) and RAM budget
  (no room for Vosk 40 MiB ASR model + daemon). The v1.3 design
  would be: Vosk small PL ASR (40 MiB) loaded on boot, energy
  VAD triggers a 1.5 s Vosk decode, gate against the keyword
  `pedro`. CPU budget is tight (~10% idle), so this is a separate
  phase once we have a session dedicated to Vosk integration.
- OpenViking lookup from runner (`searching` state with real lookup).
- Calendar write actions (Kamila calendar token has scope, but no
  intent allowed in v1.2; runner only reads existing JSON).
- Polsat/media control via voice.
- Multi-language detection (Polish-only in v1.2).
- Any UI button that triggers voice. The kiosk is still passive.
