#!/usr/bin/env python3
"""Mock Pedro Voice Console state transition script.

Demonstrates the full happy-path + error + privacy transitions defined in
03_voice_console_contract.md, by writing app/state/voice_console.json with
sequential state updates. Used for manual UI testing in Etap 1.

Usage:
    python3 scripts/mock-voice-result.py "hej Pedro, pokaż stan projektu"
    python3 scripts/mock-voice-result.py --quick    # same path, no sleeps
    python3 scripts/mock-voice-result.py --error    # finish with an error state instead of result
    python3 scripts/mock-voice-result.py --privacy  # finish with privacy_blocked instead of result
    python3 scripts/mock-voice-result.py --final-state idle|listening_for_wake|wake_detected|recording|transcribing|thinking|searching|speaking_or_result|error|privacy_blocked
    python3 scripts/mock-voice-result.py --out PATH # write to a different voice_console.json

Atomic write: temp file + os.replace(). Sleep is short by default so the
operator can watch the UI cycle through states in real time.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VOICE_STATE = PROJECT_ROOT / "app" / "state" / "voice_console.json"

PRIVACY_MODE = os.environ.get("DASHBOARD_PRIVACY_MODE", "private")

# Happy-path pipeline mirrors 03_voice_console_contract.md
HAPPY_PATH: list[tuple[str, str, bool, str]] = [
    # (state,                 activity_label,           spinner,  result_summary)
    ("listening_for_wake",   "Słucham frazy budzącej", True,    "Czekam na 'hej Pedro'."),
    ("wake_detected",        "Wykryto 'hej Pedro'",    False,   "Budzik złapany."),
    ("recording",            "Nagrywam wypowiedź",     True,    "..."),
    ("transcribing",         "Transkrybuję",           True,    "STT mock..."),
    ("thinking",             "Myślę",                  True,    "Hermes runner myśli."),
    ("searching",            "Szukam w kontekście",    True,    "OpenViking lookup (mock)."),
    ("speaking_or_result",   "Wynik gotowy",           False,   "Mock: znaleziono 0 elementów. To jest demonstracja kontraktu."),
]

ERROR_TAIL: tuple[str, str, bool, str] = (
    "error",
    "Błąd",
    False,
    "Mock error: symulowany błąd runnera.",
)

PRIVACY_TAIL: tuple[str, str, bool, str] = (
    "privacy_blocked",
    "Treść ukryta",
    False,
    "Tryb privacy blokuje wyświetlenie treści.",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _redact_public_text(value: str) -> str:
    text = str(value or "")
    patterns = [
        r"(?i)\b(api[_-]?key|token|secret|password|passwd|bearer)\b\s*[:=]?\s*\S+",
        r"(?i)\b(sk-[A-Za-z0-9_-]{16,})\b",
        r"\b[A-Za-z0-9_=-]{32,}\b",
    ]
    for pat in patterns:
        text = re.sub(pat, "[redacted]", text)
    return text


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


def _build_voice_console(state: str, label: str, spinner: bool, summary: str, utterance: str) -> dict:
    is_error = state == "error"
    is_privacy = state == "privacy_blocked"
    safe_utterance = _redact_public_text(utterance)
    partial = safe_utterance[:18] + "..." if len(safe_utterance) > 18 else safe_utterance
    final_visible_states = ("transcribing", "thinking", "searching", "speaking_or_result")
    return {
        "status": "error" if is_error else "ok",
        "updated_at": _now_iso(),
        "ttl_seconds": 10,
        "privacy_mode": PRIVACY_MODE,
        "voice": {
            "mode": "mock",
            "state": state,
            "wake_phrase": "hej Pedro",
            "mic_status": "available" if state not in ("error", "disabled") else "unknown",
            "stt_status": "busy" if state == "transcribing" else ("error" if is_error else "not_configured"),
            "runner_status": "busy" if state in ("thinking", "searching") else ("error" if is_error else "not_configured"),
        },
        "utterance": {
            "partial": partial if state == "listening_for_wake" else "",
            "final": safe_utterance if state in final_visible_states else "",
            "language": "pl",
            "confidence": 0.92 if state in final_visible_states else None,
        },
        "activity": {
            "label": label,
            "detail": f"Mock voice pipeline: {state}",
            "spinner": spinner,
        },
        "result": {
            "summary": summary,
            "requires_user_action": is_privacy,
            "clarifying_question": "Czy chodziło Ci o X?" if is_privacy else None,
        },
        "error": {
            "code": "MOCK_RUNNER_ERROR" if is_error else None,
            "message_public": "Mock błąd — brak realnego audio." if is_error else None,
            "debug_ref": "mock-debug-ref" if is_error else None,
        }
        if is_error
        else {"code": None, "message_public": None, "debug_ref": None},
    }


def _final_state_value(name: str) -> tuple[str, str, bool, str]:
    if name == "idle":
        return ("idle", "Gotowe", False, "Brak aktywnej komendy.")
    for state, label, spinner, summary in HAPPY_PATH:
        if state == name:
            return (state, label, spinner, summary)
    if name == "error":
        return ERROR_TAIL
    if name == "privacy_blocked":
        return PRIVACY_TAIL
    raise SystemExit(f"unknown final state: {name}")


def run(args: argparse.Namespace) -> int:
    sleep_s = 0.0 if args.quick else 0.3
    out = Path(args.out).resolve()
    utterance = args.utterance or "hej Pedro, pokaż stan projektu"

    # Build the path
    pipeline: list[tuple[str, str, bool, str]] = list(HAPPY_PATH)
    if args.error:
        pipeline.append(ERROR_TAIL)
    elif args.privacy:
        pipeline.append(PRIVACY_TAIL)
    elif args.final_state:
        pipeline.append(_final_state_value(args.final_state))

    print(f"writing {len(pipeline)} state(s) to {out}")
    for idx, (state, label, spinner, summary) in enumerate(pipeline, start=1):
        payload = _build_voice_console(state, label, spinner, summary, utterance)
        _atomic_write(out, payload)
        print(f"  [{idx:02d}/{len(pipeline):02d}] state={state!r:<24} label={label!r}")
        if sleep_s and idx < len(pipeline):
            time.sleep(sleep_s)

    print("done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no sleeps between state writes")
    parser.add_argument("--error", action="store_true", help="end pipeline with error state")
    parser.add_argument("--privacy", action="store_true", help="end pipeline with privacy_blocked state")
    parser.add_argument(
        "--final-state",
        choices=[
            "idle",
            "listening_for_wake",
            "wake_detected",
            "recording",
            "transcribing",
            "thinking",
            "searching",
            "speaking_or_result",
            "error",
            "privacy_blocked",
        ],
        help="override the final state of the pipeline",
    )
    parser.add_argument("--out", default=str(DEFAULT_VOICE_STATE), help="output voice_console.json path")
    parser.add_argument("utterance", nargs="?", help="mock Polish voice command to place in final transcript")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
