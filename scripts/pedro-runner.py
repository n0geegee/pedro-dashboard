#!/usr/bin/env python3
"""Pedro runner — bounded command router.

Reads the final voice_console.json state (state == speaking_or_result OR
transcribed idle text), matches the utterance against a static allowlist
(`pedro_runner_allowlist.json`), and writes back the same JSON file with
an updated `result.summary`, `voice.{stt,runner}_status`, and
`updated_at`.

Never calls the network for STT (that is `pedro-voice-stt.py`); this
script is local-only and bounded by a wall-clock timeout. Designed to be
forked from `pedro_voice_daemon.py` so a runaway runner cannot wedge the
daemon.

Exit codes:
    0  success (intent matched or `help`)
    1  empty / unreadable input
    2  intent not allowed
    3  runner timeout
    4  data source missing/stale (degraded result still written)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = PROJECT_ROOT / "app" / "state" / "voice_console.json"
ALLOWLIST = Path(__file__).resolve().parent / "pedro_runner_allowlist.json"
PRIVACY_FILE = Path(os.environ.get("PEDRO_PRIVACY_FILE",
                                   str(Path.home() / ".local" / "state" / "pedro_dashboard" / "privacy_mode")))

HARD_TIMEOUT_S = 5

PRIVACY_HINT = re.compile(
    r"\b(tryb\s*prywatn|tryb\s*normaln|tryb\s*go[śs]c|tryb\s*gosc|"
    r"private\s*mode|normal\s*mode|guest\s*mode|w[łl][aą]cz\s*prywatn|"
    r"wy[łl][aą]cz\s*prywatn)\b",
    re.IGNORECASE,
)


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


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_allowlist() -> dict:
    if not ALLOWLIST.exists():
        return {"intents": []}
    try:
        return json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"intents": []}


def _normalise(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    # Drop leading wake phrase leftovers, in case STT returned "pedro pokaż..."
    for prefix in ("pedro,", "pedro ", "pedro!", "pedro.", "hey pedro", "hej pedro"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip(" ,.")
            break
    return text


def _match_intent(text: str, allowlist: dict) -> dict | None:
    norm = _normalise(text)
    if not norm:
        return None
    for intent in allowlist.get("intents", []):
        for phrase in intent.get("phrases", []):
            p = phrase.lower()
            if p in norm or norm in p or norm.startswith(p):
                return intent
    # fallback: single-keyword match for very short utterances
    words = norm.split()
    if len(words) <= 3:
        for intent in allowlist.get("intents", []):
            for phrase in intent.get("phrases", []):
                if any(w == phrase.lower() for w in words):
                    return intent
    return None


def _read_data_source(rel: str, project_root: Path) -> dict | None:
    path = project_root / "app" / "state" / rel
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _system_summary() -> dict:
    ram_free = "?"
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    ram_free = str(kb // 1024)
                    break
    except OSError:
        pass
    pid = "?"
    pidfile = Path.home() / ".local" / "state" / "pedro_dashboard" / "run" / "dashboard.pid"
    if pidfile.exists():
        try:
            pid = pidfile.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return {"ram_free": ram_free, "pid": pid}


def _time_summary() -> dict:
    now = datetime.now().astimezone()
    return {"time": now.strftime("%H:%M, %d %B %Y").replace("January", "stycznia").replace("February", "lutego").replace("March", "marca").replace("April", "kwietnia").replace("May", "maja").replace("June", "czerwca").replace("July", "lipca").replace("August", "sierpnia").replace("September", "września").replace("October", "października").replace("November", "listopada").replace("December", "grudnia")}


def _weather_summary(data: dict | None) -> dict:
    if not data or data.get("status") not in ("ok", "stale"):
        return {"summary": "Brak aktualnej pogody. Sprawdź widget pogody."}
    payload = data.get("data") or {}
    text = payload.get("summary") or payload.get("description") or "Pogoda dostępna w widgecie."
    return {"summary": f"Pogoda: {text}."}


def _route_summary(data: dict | None) -> dict:
    if not data or data.get("status") not in ("ok", "stale"):
        return {"summary": "Brak trasy. Włącz tryb poranny albo sprawdź trasę w widgecie."}
    payload = data.get("data") or {}
    text = payload.get("summary") or "Trasa dostępna w widgecie UR."
    return {"summary": f"Trasa: {text}."}


def _volleyball_summary(data: dict | None) -> dict:
    if not data or data.get("status") not in ("ok", "stale"):
        return {"summary": "Brak terminarza siatkówki. Sprawdź widget UL."}
    payload = data.get("data") or {}
    items = payload.get("upcoming") or []
    if not items:
        return {"summary": "Brak najbliższych meczów reprezentacji Polski."}
    first = items[0]
    return {"summary": f"Najbliższy mecz: {first.get('title', '?')} — {first.get('when', '?')}."}


def _focus_summary(data: dict | None) -> dict:
    if not data or data.get("status") not in ("ok", "stale"):
        return {"summary": "Brak focusa. Sprawdź widget UL."}
    payload = data.get("data") or {}
    items = payload.get("items") or []
    if not items:
        return {"summary": "Focus nie ustawiony. Dodaj go w PROJECT_DECISIONS albo notatce."}
    first = items[0]
    return {"summary": f"Focus: {first.get('title', '?')}."}


def _set_privacy(mode: str) -> str:
    try:
        PRIVACY_FILE.parent.mkdir(parents=True, exist_ok=True)
        PRIVACY_FILE.write_text(mode, encoding="utf-8")
        return mode
    except OSError as exc:
        return f"error:{exc}"


def _build_summary(intent: dict, state: dict, project_root: Path) -> str:
    template = intent.get("summary_template") or "OK."
    sources = {name: _read_data_source(name, project_root) for name in intent.get("data_sources", [])}
    # pre-built summaries
    if "system.json" in sources:
        sources["system.json"] = _system_summary()
    if intent["id"] == "time":
        sources["__time__"] = _time_summary()
    if "weather.json" in sources:
        sources["weather.json"] = _weather_summary(sources["weather.json"])
    if "route.json" in sources:
        sources["route.json"] = _route_summary(sources["route.json"])
    if "volleyball.json" in sources:
        sources["volleyball.json"] = _volleyball_summary(sources["volleyball.json"])
    if "current_focus.json" in sources:
        sources["current_focus.json"] = _focus_summary(sources["current_focus.json"])
    if intent["id"] == "replay":
        last = (state.get("result") or {}).get("summary") or "Brak poprzedniego wyniku."
        sources["_last_summary"] = {"last": last}
    # flat merge for template
    flat: dict[str, Any] = {}
    for v in sources.values():
        if isinstance(v, dict):
            flat.update(v)
    try:
        return template.format(**flat)
    except (KeyError, IndexError):
        # template refers to a missing key; degrade to a safe sentence
        return "Komenda zrozumiana, ale brakuje danych do odpowiedzi. Sprawdź widget."


class _Timeout:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self._previous = None

    def __enter__(self):
        def _handler(signum, frame):
            raise TimeoutError("runner timeout")
        self._previous = signal.signal(signal.SIGALRM, _handler)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)
        return self

    def __exit__(self, exc_type, exc, tb):
        signal.setitimer(signal.ITIMER_REAL, 0)
        if self._previous is not None:
            signal.signal(signal.SIGALRM, self._previous)


def run(args: argparse.Namespace) -> int:
    state_path = Path(args.state).resolve()
    started = time.time()
    try:
        with _Timeout(HARD_TIMEOUT_S):
            state = _load_state(state_path)
            if not state:
                print(json.dumps({"ok": False, "error": "missing state"}))
                return 1
            utterance = (state.get("utterance") or {}).get("final") or ""
            allowlist = _load_allowlist()
            intent = _match_intent(utterance, allowlist)
            if not intent:
                state["voice"]["runner_status"] = "error"
                state["activity"] = {
                    "label": "Nie rozpoznano",
                    "detail": "Komenda spoza allowlist.",
                    "spinner": False,
                }
                state["result"] = {
                    "summary": "Nie rozpoznano komendy. Powiedz 'pomoc' żeby zobaczyć listę.",
                    "requires_user_action": False,
                    "clarifying_question": None,
                }
                state["error"] = {
                    "code": "INTENT_NOT_ALLOWED",
                    "message_public": "Komenda spoza listy dozwolonych.",
                    "debug_ref": None,
                }
                state["updated_at"] = _now_iso()
                _atomic_write(state_path, state)
                print(json.dumps({"ok": False, "error": "INTENT_NOT_ALLOWED"}))
                return 2

            # Privacy actions
            if "set_privacy" in intent:
                mode = _set_privacy(intent["set_privacy"])
                state["privacy_mode"] = mode if not mode.startswith("error:") else state.get("privacy_mode", "normal")

            summary = _build_summary(intent, state, PROJECT_ROOT)
            state["voice"]["runner_status"] = "ready"
            state["activity"] = {
                "label": "Wynik",
                "detail": intent["id"],
                "spinner": False,
            }
            state["result"] = {
                "summary": summary,
                "requires_user_action": False,
                "clarifying_question": None,
            }
            state["error"] = {"code": None, "message_public": None, "debug_ref": None}
            state["updated_at"] = _now_iso()
            _atomic_write(state_path, state)
            print(json.dumps({"ok": True, "intent": intent["id"],
                              "summary": summary, "elapsed_s": round(time.time() - started, 2)}))
            return 0
    except TimeoutError:
        print(json.dumps({"ok": False, "error": "RUNNER_TIMEOUT", "elapsed_s": round(time.time() - started, 2)}))
        return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="path to voice_console.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="print matched intent for the current state, do not write")
    args = parser.parse_args(argv)

    if args.dry_run:
        state = _load_state(Path(args.state))
        utterance = (state.get("utterance") or {}).get("final") or ""
        allowlist = _load_allowlist()
        intent = _match_intent(utterance, allowlist)
        print(json.dumps({"ok": intent is not None, "intent": (intent or {}).get("id"),
                          "utterance": utterance}, ensure_ascii=False))
        return 0 if intent else 2

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
