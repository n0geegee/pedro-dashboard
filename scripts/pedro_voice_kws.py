#!/usr/bin/env python3
"""Pedro voice KWS daemon — always-listening "hey pedro" on iMac built-in mic.

Architecture (post-AGENTS.md review, replaces v1.3 push-to-talk which could
never trigger because the iMac has no keyboard):

    arecord plughw:0,2 16k mono
        │
        ▼
    Vosk small-pl streaming recognizer (RTF 0.44 measured, real-time)
        │  partial text contains "pedro"/"hej pedro"/"hey pedro"
        ▼
    arecord 4 s command audio ──► pedro-voice-stt.py (Gemini)
        │                          │
        ▼                          ▼
    voice_console.json ◄── pedro-runner.py (allowlist router)
        │
        ▼
    pedro-voice-tts.py (espeak-ng, pl)

State contract (writes app/state/voice_console.json):

    mode: "kws"                       # always-listening
    state: idle | wake_detected | listening_command | processing | result | error
    mic_status: ok | error
    stt_status: configured | error
    runner_status: configured | error

Exit codes:
    0  clean shutdown (SIGTERM / SIGINT)
    1  CLI / arg error
    2  model missing
    3  mic open failed
    4  fatal exception in main loop
    5  env (Gemini key) missing
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import wave
import queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Paths -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
STATE_PATH = PROJECT_ROOT / "app" / "state" / "voice_console.json"
VOSK_MODEL = Path(os.environ.get(
    "PEDRO_VOSK_MODEL",
    str(Path.home() / ".local" / "share" / "vosk" / "models" / "small-pl"),
))
PID_PATH = Path(os.environ.get(
    "PEDRO_VOICE_DAEMON_PID",
    str(Path.home() / ".local" / "state" / "pedro_dashboard" / "run" / "voice_kws.pid"),
))
# Legacy alias: refresh-voice-console.py looks at voice_daemon.pid to know
# whether a real daemon is running. We keep both in sync so the refresher
# does not race us and repaint the file with stale "listening_for_wake".
LEGACY_PID_PATH = Path(os.environ.get(
    "PEDRO_VOICE_DAEMON_LEGACY_PID",
    str(Path.home() / ".local" / "state" / "pedro_dashboard" / "run" / "voice_daemon.pid"),
))
LOG_PATH = Path(os.environ.get(
    "PEDRO_VOICE_KWS_LOG",
    str(Path.home() / ".local" / "state" / "pedro_dashboard" / "logs" / "voice_kws.log"),
))

# --- Audio / KWS tuning ------------------------------------------------------

ARE_DEV = os.environ.get("PEDRO_MIC_DEV", "plughw:0,2")
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_MS = 200  # 200 ms blocks = vosk sees ~5 blocks/s, partial update latency < 1 s
COMMAND_SECONDS = 4.0  # how long to record after "pedro" detected

# Wake-word detection. Vosk PL model renders "hej pedro" / "pedro" / "hey pedro"
# in many ways; we match all common spellings in partial text.
WAKE_RE = re.compile(
    r"\b("
    r"hej\s*pedro|"
    r"hey\s*pedro|"
    r"ej\s*pedro|"
    r"hej\s*petro|"
    r"pedro|"
    r"petro"
    r")\b",
    re.IGNORECASE,
)
# Word-level: when vosk returns partial, check if 'pedro' or 'petro' appears.

COOLDOWN_S = 2.0        # minimum seconds between wake detections
ENERGY_GATE = 250       # RMS gate: skip frames quieter than this (out of 32768)
RECORD_PADDING_S = 0.4  # prepend this much of pre-wake audio into the command WAV

# --- State write helpers -----------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _base_state() -> dict:
    """Base state when KWS daemon owns the file."""
    return {
        "status": "ok",
        "updated_at": _now_iso(),
        "ttl_seconds": 60,
        "privacy_mode": _read_privacy(),
        "voice": {
            "mode": "kws",
            "state": "idle",
            "wake_phrase": "hej pedro",
            "mic_status": "ok",
            "stt_status": "configured",
            "runner_status": "configured",
        },
        "utterance": {"partial": "", "final": "", "language": "pl", "confidence": None},
        "activity": {
            "label": "Nasłuchuję",
            "detail": "Powiedz 'hej Pedro' albo 'Pedro' żeby wywołać komendę.",
            "spinner": False,
        },
        "result": {"summary": "", "requires_user_action": False, "clarifying_question": None},
        "error": {"code": None, "message_public": None, "debug_ref": None},
    }


def _read_privacy() -> str:
    pf = Path(os.environ.get(
        "PEDRO_PRIVACY_FILE",
        str(Path.home() / ".local" / "state" / "pedro_dashboard" / "privacy_mode"),
    ))
    if not pf.exists():
        return "private"
    try:
        v = pf.read_text(encoding="utf-8").strip().lower()
        return v if v in ("private", "normal", "guest") else "private"
    except OSError:
        return "private"


def _publish(state: dict) -> None:
    state["updated_at"] = _now_iso()
    _atomic_write(STATE_PATH, state)


# --- Logging -----------------------------------------------------------------

_log_lock = threading.Lock()


def _log(msg: str) -> None:
    line = f"{_now_iso()} [kws] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _log_lock:
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError:
        pass


# --- Audio capture -----------------------------------------------------------

def _open_arecord() -> subprocess.Popen:
    """Spawn arecord streaming 16 kHz mono 16-bit s16le to stdout."""
    return subprocess.Popen(
        [
            "arecord",
            "-D", ARE_DEV,
            "-q",                          # quiet
            "-r", str(SAMPLE_RATE),
            "-c", str(CHANNELS),
            "-f", "S16_LE",
            "-t", "raw",                   # raw s16le to stdout
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )


def _rms(block: bytes) -> int:
    """Root-mean-square of signed-16-bit little-endian samples."""
    n = len(block) // 2
    if n == 0:
        return 0
    import struct
    samples = struct.unpack(f"<{n}h", block)
    sq = sum(s * s for s in samples) / n
    return int(sq ** 0.5)


# --- Command capture + STT + runner + TTS ------------------------------------

def _capture_command(seconds: float) -> Path:
    """Record `seconds` of audio after wake detection to a temp WAV file."""
    out = Path("/tmp") / f"pedro-cmd-{int(time.time()*1000)}.wav"
    proc = subprocess.Popen(
        [
            "arecord",
            "-D", ARE_DEV,
            "-q",
            "-r", str(SAMPLE_RATE),
            "-c", str(CHANNELS),
            "-f", "S16_LE",
            "-d", str(int(seconds + 0.5)),
            "-t", "wav",
            str(out),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    rc = proc.wait()
    if rc != 0 or not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError(f"arecord command capture failed (rc={rc}, file={out})")
    return out


def _run_stt(wav: Path) -> str:
    """Run pedro-voice-stt.py transcribe on a wav; return final text or ''."""
    r = subprocess.run(
        [str(SCRIPTS / "pedro-voice-stt.py"), "transcribe", str(wav)],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        _log(f"STT exit={r.returncode} stderr={r.stderr.strip()[:200]}")
        return ""
    text = (r.stdout or "").strip()
    if text in ("<UNK>", ""):
        return ""
    return text


def _run_tts(text: str) -> None:
    """Run pedro-voice-tts.py, fire-and-forget (don't block KWS on speech)."""
    if not text:
        return
    try:
        subprocess.Popen(
            [str(SCRIPTS / "pedro-voice-tts.py"), text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        _log(f"TTS spawn failed: {exc}")


def _run_runner(state: dict) -> dict:
    """Run pedro-runner.py against current state; return updated state."""
    _publish(state)  # ensure latest state on disk before runner reads it
    r = subprocess.run(
        [str(SCRIPTS / "pedro-runner.py"), "--state", str(STATE_PATH)],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode not in (0, 2):
        _log(f"runner exit={r.returncode} stderr={r.stderr.strip()[:200]}")
    return _read_state(STATE_PATH)


# --- Main KWS loop -----------------------------------------------------------

class KwsRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.state = _base_state()
        self._stop = threading.Event()
        self._processing = threading.Event()  # when set, KWS pauses for STT/runner
        self._last_wake = 0.0
        self._state_lock = threading.Lock()

    def stop(self, *_: Any) -> None:
        self._stop.set()

    def _publish_state(self, **overrides: Any) -> None:
        with self._state_lock:
            for k, v in overrides.items():
                if k in ("activity", "utterance", "result", "error", "voice"):
                    self.state[k].update(v) if isinstance(v, dict) else setattr(self.state, k, v)
                else:
                    self.state[k] = v
            _publish(self.state)

    def _handle_command_audio(self, wav: Path) -> None:
        """Run STT → runner → TTS, then return to KWS listening."""
        self._processing.set()
        try:
            self._publish_state(
                voice={"state": "processing"},
                activity={"label": "Transkrybuję", "detail": "Wysyłam do Gemini…", "spinner": True},
            )
            text = _run_stt(wav)
            if not text:
                _run_tts("Nie zrozumiałem. Powtórz proszę.")
                self._publish_state(
                    voice={"state": "result", "runner_status": "error"},
                    activity={"label": "Nie zrozumiano", "detail": "Brak transkrypcji.", "spinner": False},
                    result={"summary": "Nie zrozumiałem komendy. Powiedz 'hej Pedro' jeszcze raz.", "requires_user_action": False, "clarifying_question": None},
                    error={"code": "STT_EMPTY", "message_public": "Brak transkrypcji.", "debug_ref": None},
                )
                return

            self._publish_state(
                utterance={"final": text, "partial": "", "language": "pl", "confidence": None},
                activity={"label": "Rozpoznano", "detail": text, "spinner": False},
            )
            new_state = _run_runner(self.state)
            with self._state_lock:
                self.state = new_state

            summary = (self.state.get("result") or {}).get("summary") or ""
            _run_tts(summary)
        except subprocess.TimeoutExpired as exc:
            _log(f"command handling timeout: {exc}")
            _run_tts("Przekroczono czas. Spróbuj ponownie.")
        except Exception as exc:  # noqa: BLE001
            _log(f"command handling error: {exc!r}")
            _run_tts("Coś poszło nie tak. Spróbuj ponownie.")
            self._publish_state(
                voice={"state": "error"},
                error={"code": "KWS_HANDLER_FAIL", "message_public": "Błąd obsługi komendy.", "debug_ref": None},
            )
        finally:
            self._processing.clear()
            # Reset to idle
            self._publish_state(
                voice={"state": "idle"},
                utterance={"partial": "", "final": "", "language": "pl", "confidence": None},
                activity={
                    "label": "Nasłuchuję",
                    "detail": "Powiedz 'hej Pedro' albo 'Pedro' żeby wywołać komendę.",
                    "spinner": False,
                },
                result={"summary": "", "requires_user_action": False, "clarifying_question": None},
                error={"code": None, "message_public": None, "debug_ref": None},
            )

    def run(self) -> int:
        # Vosk import is heavy (~3 s); do it after state is published.
        import vosk  # type: ignore

        if not VOSK_MODEL.exists():
            _log(f"Vosk model not found at {VOSK_MODEL}")
            return 2

        if not (Path.home() / ".hermes" / ".env").exists():
            _log("~/.hermes/.env missing — Gemini key required for STT")
            return 5

        _log(f"loading Vosk model: {VOSK_MODEL}")
        t0 = time.time()
        model = vosk.Model(str(VOSK_MODEL))
        rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
        rec.SetWords(True)
        _log(f"Vosk loaded in {time.time()-t0:.1f}s")

        self._publish_state()
        _log("KWS daemon started")

        arec = _open_arecord()
        if arec.stdout is None:
            _log("arecord stdout is None — mic open failed")
            return 3

        block_bytes = SAMPLE_RATE * CHANNELS * 2 * BLOCK_MS // 1000  # 200 ms = 6400 bytes
        wake_pending: queue.Queue[Path] = queue.Queue()
        first_block_after_wake: list[bytes] = []
        in_wake = False
        last_heartbeat = 0.0
        HEARTBEAT_S = 3.0  # refresh updated_at even in idle so UI knows daemon is alive

        try:
            while not self._stop.is_set():
                # If a command is being processed, drop audio but keep arecord alive
                if self._processing.is_set():
                    arec.stdout.read(block_bytes)
                    time.sleep(0.01)
                    continue

                # Idle heartbeat: repaint updated_at so the UI sees the daemon alive
                now = time.time()
                if now - last_heartbeat >= HEARTBEAT_S:
                    self._publish_state()
                    last_heartbeat = now

                block = arec.stdout.read(block_bytes)
                if not block:
                    if self._stop.is_set():
                        return 0  # graceful shutdown, not an error
                    _log("arecord closed stream — mic unplugged?")
                    return 4
                if len(block) < block_bytes:
                    # partial block; skip
                    continue

                if in_wake:
                    first_block_after_wake.append(block)
                    if len(first_block_after_wake) * BLOCK_MS >= 1000 * RECORD_PADDING_S:
                        in_wake = False
                        # Will continue capturing in the next phase
                    continue

                # Update partial transcription
                if rec.AcceptWaveform(block):
                    res = json.loads(rec.Result())
                    text = res.get("text", "")
                    if text:
                        self._publish_state(
                            utterance={"final": text, "partial": "", "language": "pl",
                                       "confidence": res.get("confidence")},
                        )
                else:
                    pres = json.loads(rec.PartialResult())
                    partial = pres.get("partial", "")
                    if partial:
                        self._publish_state(utterance={"partial": partial})
                        if WAKE_RE.search(partial) and (time.time() - self._last_wake) > COOLDOWN_S:
                            self._last_wake = time.time()
                            _log(f"WAKE detected: {partial!r}")
                            self._publish_state(
                                voice={"state": "wake_detected"},
                                activity={"label": "Słyszę 'Pedro'", "detail": "Nagrywam komendę…", "spinner": True},
                            )
                            # Spawn handler thread that captures 4 s, runs STT/runner/TTS
                            t = threading.Thread(
                                target=self._handle_command_audio,
                                args=(_capture_command(COMMAND_SECONDS),),
                                daemon=True,
                            )
                            t.start()
        finally:
            try:
                arec.terminate()
                arec.wait(timeout=2)
            except Exception:  # noqa: BLE001
                pass
            self._publish_state(
                voice={"state": "idle", "mode": "kws"},
                activity={"label": "KWS zatrzymany", "detail": "Daemon wyłączony.", "spinner": False},
            )
            _log("KWS daemon stopped")
        return 0


# --- CLI ---------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=str(VOSK_MODEL), help="path to Vosk model dir")
    parser.add_argument("--mic", default=ARE_DEV, help="ALSA capture device (default plughw:0,2)")
    parser.add_argument("--command-seconds", type=float, default=COMMAND_SECONDS,
                        help="seconds to record after wake detected")
    args = parser.parse_args(argv)

    if args.model:
        os.environ["PEDRO_VOSK_MODEL"] = args.model
    if args.mic:
        os.environ["PEDRO_MIC_DEV"] = args.mic
    if args.command_seconds:
        os.environ["PEDRO_COMMAND_SECONDS"] = str(args.command_seconds)

    # Write PID (both new + legacy alias so refresh-voice-console.py sees us)
    try:
        PID_PATH.parent.mkdir(parents=True, exist_ok=True)
        PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
        LEGACY_PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except OSError as exc:
        print(f"warning: cannot write pid: {exc}", file=sys.stderr)

    runner = KwsRunner(args)
    signal.signal(signal.SIGTERM, runner.stop)
    signal.signal(signal.SIGINT, runner.stop)
    try:
        return runner.run()
    finally:
        try:
            PID_PATH.unlink(missing_ok=True)
            LEGACY_PID_PATH.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
