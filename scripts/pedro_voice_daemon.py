#!/usr/bin/env python3
"""Pedro voice daemon — long-lived push-to-talk controller.

Polls the X11 keyboard state at ~20 Hz and watches a single trigger key
(default Space, overridable via PEDRO_VOICE_TRIGGER_KEYCODE). While the
key is held, the daemon captures audio from ALSA, then runs the
state-machine pipeline:

  recording → transcribing (Gemini STT) → hey-pedro prefix gate →
  thinking (runner allowlist) → speaking_or_result (espeak-ng TTS) →
  cooldown → listening_for_wake

State is written atomically to app/state/voice_console.json so the
kiosk frontend stays the single source of truth. The daemon never blocks
the X server and never grabs the key; the keystroke still reaches the
kiosk Chrome.

This script deliberately avoids onnxruntime / tflite-runtime / openwakeword
because the iMac-Hermes CPU (Core 2 Duo T7700, flags
sse sse2 ssse3 only) crashes those libraries with SIGILL. The "hey pedro"
phrase is enforced as a prefix gate on the Gemini transcript, not as an
audio-side KWS.

Exit codes:
    0  normal exit (SIGTERM from watchdog)
    1  fatal: missing X display
    2  fatal: missing python-xlib
    3  fatal: missing ALSA capture binary
    4  fatal: state path unwritable
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = PROJECT_ROOT / "app" / "state" / "voice_console.json"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
RECORD_SCRIPT = SCRIPTS_DIR / "pedro-voice-record.py"
STT_SCRIPT = SCRIPTS_DIR / "pedro-voice-stt.py"
TTS_SCRIPT = SCRIPTS_DIR / "pedro-voice-tts.py"
RUNNER_SCRIPT = SCRIPTS_DIR / "pedro-runner.py"
PID_FILE = Path(os.environ.get(
    "PEDRO_VOICE_DAEMON_PID",
    str(Path.home() / ".local" / "state" / "pedro_dashboard" / "run" / "voice_daemon.pid"),
))
LOG_FILE = Path(os.environ.get(
    "PEDRO_VOICE_DAEMON_LOG",
    str(Path.home() / ".local" / "state" / "pedro_dashboard" / "logs" / "voice_daemon.log"),
))

POLL_HZ = 20
POLL_PERIOD = 1.0 / POLL_HZ
MAX_HOLD_S = 5.0
COOLDOWN_S = 1.5
DEFAULT_KEYCODE = int(os.environ.get("PEDRO_VOICE_TRIGGER_KEYCODE", "65"))  # Space
WAKE_PREFIXES = ("hey pedro", "hej pedro", "pedro")
WAV_PATH = Path("/tmp") / "pedro-voice-capture.wav"

PRIVACY_HINT_RE = re.compile(
    r"\b(tryb\s*prywatn|tryb\s*normaln|tryb\s*go[śs]c|tryb\s*gosc)\b",
    re.IGNORECASE,
)

SHUTDOWN = False


def _log(msg: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


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


def _write_state(path: Path, voice: dict, activity: dict, result: dict, error: dict,
                 privacy_mode: str, status: str = "ok") -> None:
    state = _read_state(path) or {
        "status": "ok",
        "ttl_seconds": 30,
        "utterance": {"partial": "", "final": "", "language": "pl", "confidence": None},
    }
    state["status"] = status
    state["updated_at"] = _now_iso()
    state["privacy_mode"] = privacy_mode
    state["voice"] = voice
    state["activity"] = activity
    state["result"] = result
    state["error"] = error
    _atomic_write(path, state)


def _is_pressed(keys: bytes, keycode: int) -> bool:
    if not keys:
        return False
    byte_idx = (keycode - 1) // 8
    bit_idx = (keycode - 1) % 8
    if byte_idx < 0 or byte_idx >= len(keys):
        return False
    return bool(keys[byte_idx] & (1 << bit_idx))


def _read_privacy() -> str:
    pf = Path(os.environ.get(
        "PEDRO_PRIVACY_FILE",
        str(Path.home() / ".local" / "state" / "pedro_dashboard" / "privacy_mode"),
    ))
    if pf.exists():
        try:
            v = pf.read_text(encoding="utf-8").strip().lower()
            if v in ("normal", "private", "guest"):
                return v
        except OSError:
            pass
    return "private"


def _idle_voice(privacy: str, mic: str = "available", stt: str = "ready", runner: str = "ready") -> dict:
    return {
        "mode": "wake_word",
        "state": "listening_for_wake",
        "wake_phrase": "hey pedro",
        "mic_status": mic,
        "stt_status": stt,
        "runner_status": runner,
    }


def _idle_activity() -> dict:
    return {
        "label": "Słucham",
        "detail": "Przytrzymaj klawisz i powiedz 'hey pedro, <komenda>'.",
        "spinner": False,
    }


def _idle_result() -> dict:
    return {"summary": "Brak aktywnej komendy.", "requires_user_action": False,
            "clarifying_question": None}


def _empty_error() -> dict:
    return {"code": None, "message_public": None, "debug_ref": None}


def _strip_wake(text: str) -> str:
    norm = unicodedata.normalize("NFKC", text).lower().strip()
    # remove leading punctuation/whitespace
    norm = re.sub(r"^[\s\.,;:!\?]+", "", norm)
    for prefix in WAKE_PREFIXES:
        if norm.startswith(prefix):
            rest = norm[len(prefix):]
            rest = re.sub(r"^[\s\.,;:!\?]+", "", rest)
            return rest
    return ""


def _run_capture(duration: float, device: str) -> int:
    cmd = [
        sys.executable,
        str(RECORD_SCRIPT),
        "--duration", str(duration),
        "--device", device,
        "--out", str(WAV_PATH),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=duration + 8, check=False)
    except subprocess.TimeoutExpired:
        return 124
    return proc.returncode


def _run_stt() -> tuple[int, str]:
    try:
        proc = subprocess.run(
            [sys.executable, str(STT_SCRIPT), "transcribe", str(WAV_PATH)],
            capture_output=True, timeout=10, check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, ""
    text = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    # If STT printed multiple lines, take the last non-empty
    lines = [l for l in text.splitlines() if l.strip()]
    return proc.returncode, (lines[-1] if lines else "")


def _run_tts(text: str) -> int:
    try:
        proc = subprocess.run(
            [sys.executable, str(TTS_SCRIPT), text],
            capture_output=True, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired:
        return 124
    return proc.returncode


def _run_runner(state_path: Path) -> int:
    try:
        proc = subprocess.run(
            [sys.executable, str(RUNNER_SCRIPT), "--state", str(state_path)],
            capture_output=True, timeout=8, check=False,
        )
    except subprocess.TimeoutExpired:
        return 124
    return proc.returncode


def _handle_capture(state_path: Path, privacy: str, device: str) -> str:
    """Run the full capture+STT+gate+runner+TTS pipeline after a hold release.
    Returns the final state name to write to JSON."""
    # Step 1: capture (we already detected the press; record up to 4 s)
    _write_state(state_path,
                 voice={**_idle_voice(privacy), "state": "recording",
                        "mic_status": "busy"},
                 activity={"label": "Nagrywam",
                           "detail": "Zapisuję audio.",
                           "spinner": True},
                 result=_idle_result(),
                 error=_empty_error(),
                 privacy_mode=privacy)
    cap_rc = _run_capture(min(MAX_HOLD_S, 4.0), device)
    if cap_rc not in (0, 2):
        _write_state(state_path,
                     voice={**_idle_voice(privacy), "state": "error",
                            "mic_status": "error"},
                     activity={"label": "Błąd mikrofonu",
                               "detail": f"arecord rc={cap_rc}",
                               "spinner": False},
                     result={"summary": "Nie słyszę mikrofonu. Sprawdź ALSA.",
                             "requires_user_action": False, "clarifying_question": None},
                     error={"code": "AUDIO_CAPTURE_FAILED",
                            "message_public": "Błąd mikrofonu.",
                            "debug_ref": None},
                     privacy_mode=privacy,
                     status="error")
        _run_tts("Nie słyszę mikrofonu.")
        return "error"
    if cap_rc == 2:
        # silence detected
        _write_state(state_path,
                     voice={**_idle_voice(privacy), "state": "idle"},
                     activity={"label": "Cisza",
                               "detail": "arecord złapał ciszę.",
                               "spinner": False},
                     result=_idle_result(),
                     error=_empty_error(),
                     privacy_mode=privacy)
        return "idle"

    # Step 2: transcribe
    _write_state(state_path,
                 voice={**_idle_voice(privacy), "state": "transcribing",
                        "stt_status": "busy"},
                 activity={"label": "Transkrybuję", "detail": "Wysyłam audio do STT.",
                           "spinner": True},
                 result=_idle_result(),
                 error=_empty_error(),
                 privacy_mode=privacy)
    _log("state -> transcribing")

    rc, text = _run_stt()
    if rc != 0 or not text:
        _write_state(state_path,
                     voice={**_idle_voice(privacy), "state": "error",
                            "stt_status": "error"},
                     activity={"label": "Błąd STT",
                               "detail": f"Nie udało się rozpoznać mowy (rc={rc}).",
                               "spinner": False},
                     result={"summary": "Nie zrozumiałem. Spróbuj jeszcze raz.",
                             "requires_user_action": False, "clarifying_question": None},
                     error={"code": "STT_UPSTREAM_ERROR", "message_public": "Błąd STT.",
                            "debug_ref": None},
                     privacy_mode=privacy,
                     status="error")
        _run_tts("Nie zrozumiałem. Spróbuj jeszcze raz.")
        return "error"

    text = text.strip()
    _log(f"stt text: {text!r}")

    command = _strip_wake(text)
    if not command:
        _write_state(state_path,
                     voice={**_idle_voice(privacy), "state": "privacy_blocked",
                            "stt_status": "ready"},
                     activity={"label": "Brak 'hey pedro'",
                               "detail": "Wypowiedź nie zaczyna się od frazy 'hey pedro'.",
                               "spinner": False},
                     result={"summary": "Nie usłyszałem 'hey pedro'.",
                             "requires_user_action": False, "clarifying_question": None},
                     error={"code": "WAKE_PHRASE_NOT_DETECTED",
                            "message_public": "Powiedz 'hey pedro' przed komendą.",
                            "debug_ref": None},
                     privacy_mode=privacy)
        _run_tts("Powiedz hey pedro przed komendą.")
        return "privacy_blocked"

    # write intermediate state with the final command so runner sees it
    state = _read_state(state_path) or {}
    state["status"] = "ok"
    state["updated_at"] = _now_iso()
    state["privacy_mode"] = privacy
    state["voice"] = {**_idle_voice(privacy), "state": "thinking",
                      "runner_status": "busy"}
    state["activity"] = {"label": "Myślę", "detail": "Runner przetwarza komendę.",
                         "spinner": True}
    state["utterance"] = {"partial": "", "final": command, "language": "pl", "confidence": None}
    state["result"] = _idle_result()
    state["error"] = _empty_error()
    _atomic_write(state_path, state)
    _log(f"state -> thinking, command={command!r}")

    rc = _run_runner(state_path)
    if rc not in (0, 2):
        _log(f"runner rc={rc}")
        # runner already wrote its own error/success JSON
        _run_tts("Błąd runnera.")
        return "error"

    # read what the runner wrote
    state = _read_state(state_path) or {}
    summary = (state.get("result") or {}).get("summary") or "Gotowe."
    intent_id = (state.get("activity") or {}).get("detail") or ""

    # speak the result
    _write_state(state_path,
                 voice={**_idle_voice(privacy), "state": "speaking_or_result"},
                 activity={"label": "Mówię", "detail": intent_id, "spinner": True},
                 result=state.get("result") or _idle_result(),
                 error=_empty_error(),
                 privacy_mode=privacy)
    _log(f"state -> speaking, summary={summary!r}")
    _run_tts(summary)

    # privacy mode changes from runner are already applied via the privacy file
    return "speaking_or_result"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":0"))
    parser.add_argument("--keycode", type=int, default=DEFAULT_KEYCODE)
    parser.add_argument("--device", default=os.environ.get("PEDRO_MIC_DEVICE", "plughw:0,0"))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--once", action="store_true",
                        help="run a single capture cycle and exit (test mode)")
    args = parser.parse_args(argv)

    state_path = Path(args.state).resolve()

    # Pre-flight checks
    try:
        from Xlib import display as xdisplay
    except ImportError:
        print("python-xlib not installed; run: pip install python-xlib", file=sys.stderr)
        return 2

    if not RECORD_SCRIPT.exists() or not STT_SCRIPT.exists() or not TTS_SCRIPT.exists() or not RUNNER_SCRIPT.exists():
        print("voice scripts missing in scripts/", file=sys.stderr)
        return 4

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    def _shutdown(_sig, _frm):
        global SHUTDOWN
        SHUTDOWN = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        d = xdisplay.Display(args.display)
    except Exception as exc:
        _log(f"fatal: cannot open X display {args.display!r}: {exc}")
        return 1

    _log(f"daemon start: pid={os.getpid()} display={args.display} keycode={args.keycode} device={args.device}")

    privacy = _read_privacy()
    _write_state(state_path,
                 voice=_idle_voice(privacy),
                 activity=_idle_activity(),
                 result=_idle_result(),
                 error=_empty_error(),
                 privacy_mode=privacy)

    held_since = 0.0
    try:
        while not SHUTDOWN:
            loop_start = time.time()
            try:
                keys = d.query_keymap()
            except Exception as exc:
                _log(f"x query_keymap failed: {exc}")
                time.sleep(0.5)
                continue
            pressed = _is_pressed(keys, args.keycode)
            now = loop_start

            if pressed and held_since == 0.0:
                held_since = now
                privacy = _read_privacy()
                _write_state(state_path,
                             voice={**_idle_voice(privacy), "state": "wake_detected"},
                             activity={"label": "Wykryto klawisz",
                                       "detail": "Zacznij mówić: 'hey pedro, ...'.",
                                       "spinner": True},
                             result=_idle_result(),
                             error=_empty_error(),
                             privacy_mode=privacy)
                _log("wake_detected (key down)")

            if pressed and held_since > 0.0:
                hold_dur = now - held_since
                if hold_dur >= MAX_HOLD_S:
                    # hard cap; release implicitly and run pipeline
                    _log("hold cap reached; releasing")
                    held_since = 0.0
                    _handle_capture(state_path, privacy, args.device)
                    privacy = _read_privacy()
                    _write_state(state_path,
                                 voice=_idle_voice(privacy),
                                 activity=_idle_activity(),
                                 result=_idle_result(),
                                 error=_empty_error(),
                                 privacy_mode=privacy)
                    time.sleep(COOLDOWN_S)
                    continue

            if not pressed and held_since > 0.0:
                # released: run pipeline
                _log("key released; running pipeline")
                held_since = 0.0
                _handle_capture(state_path, privacy, args.device)
                privacy = _read_privacy()
                _write_state(state_path,
                             voice=_idle_voice(privacy),
                             activity=_idle_activity(),
                             result=_idle_result(),
                             error=_empty_error(),
                             privacy_mode=privacy)
                time.sleep(COOLDOWN_S)
                continue

            elapsed = time.time() - loop_start
            sleep_for = POLL_PERIOD - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)

            if args.once:
                break
    finally:
        _log("daemon exiting")
        try:
            PID_FILE.unlink()
        except OSError:
            pass
        try:
            WAV_PATH.unlink()
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
