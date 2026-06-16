#!/usr/bin/env python3
"""Pedro voice — STT via Google Gemini multimodal audio.

Sends a short WAV to Gemini (gemini-2.0-flash by default) and returns the
literal Polish transcription. Two modes:

  * transcribe <wav>            — full command STT after the wake phrase
  * confirm_pedro <wav>         — YES/NO gate for the wake phrase

Uses only stdlib + urllib (no extra deps; hermes-agent venv has requests
but we want zero coupling for the kiosk). Reads GEMINI_API_KEY from
~/.hermes/.env if not already in env.

Exit codes:
    0  success (text on stdout, single line, stripped)
    2  api key missing
    3  file missing/empty
    4  http 4xx
    5  http 5xx
    6  timeout
    7  parse error (no text part in response)
    8  gemini refused (safety / unsupported mime)
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-flash-latest"
TIMEOUT_S = 8
MAX_AUDIO_BYTES = 6 * 1024 * 1024  # 6 MiB hard cap; ~ 4 s @ 16 kHz mono is ~ 128 KiB

TRANSCRIBE_PROMPT = (
    'This audio starts with the Polish wake phrase "hey pedro" and then '
    'contains a short Polish voice command. Transcribe ONLY the part AFTER '
    'the wake phrase (i.e. the command itself). Output the literal Polish '
    'transcription, no quotes, no commentary, no leading "pedro" / "Pedro". '
    'If you cannot hear any command after the wake phrase, output the '
    'single word: <UNK>.'
)

CONFIRM_PROMPT = (
    'Does this audio contain the name "Pedro" spoken in Polish '
    '(sounds like "pedro", "Pedro", "Pédro", or close variants)? '
    'Reply with exactly one word: YES or NO.'
)

ENV_FILE_CANDIDATES = [
    Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / ".env",
    Path.home() / ".hermes" / ".env",
]


def _load_api_key() -> str:
    for env_path in ENV_FILE_CANDIDATES:
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v:
                    os.environ.setdefault(k, v)
        except OSError:
            pass
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(name)
        if val:
            return val
    return ""


def _mime_for(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "audio/wav"


def _read_audio(path: Path) -> bytes:
    data = path.read_bytes()
    if not data:
        raise ValueError("empty file")
    if len(data) > MAX_AUDIO_BYTES:
        raise ValueError(f"audio too large: {len(data)} bytes (cap {MAX_AUDIO_BYTES})")
    return data


def _post(url: str, body: dict, timeout_s: int) -> dict:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {"status": resp.status, "body": raw}
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"status": exc.code, "body": raw, "error": str(exc)}
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        return {"status": 0, "body": "", "error": str(exc)}


def _extract_text(response: dict) -> tuple[str, str]:
    """Returns (text, finish_reason). Empty text on safety/parse issues."""
    if "candidates" not in response or not response["candidates"]:
        return "", "no_candidates"
    cand = response["candidates"][0]
    finish = cand.get("finishReason", "")
    parts = cand.get("content", {}).get("parts", [])
    for part in parts:
        if isinstance(part, dict) and "text" in part:
            return str(part["text"]), finish
    return "", finish or "empty_parts"


def _call_gemini(audio_b64: str, mime: str, prompt: str, model: str) -> dict:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={_load_api_key()}"
    )
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": mime,
                        "data": audio_b64,
                    }
                },
            ],
        }],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 128,
        },
    }
    return _post(url, body, TIMEOUT_S)


def _call_with_fallback(audio_b64: str, mime: str, prompt: str) -> dict:
    last = {}
    for model in (DEFAULT_MODEL, FALLBACK_MODEL):
        result = _call_gemini(audio_b64, mime, prompt, model)
        if result.get("status") == 200:
            try:
                return {"ok": True, "model": model, "response": json.loads(result["body"])}
            except json.JSONDecodeError as exc:
                return {"ok": False, "error": f"json decode: {exc}", "raw": result["body"][:400]}
        if result.get("status") in (404,):
            last = result
            continue  # try fallback model
        # any other non-200 is terminal
        return {"ok": False, "model": model, "status": result.get("status"),
                "error": result.get("error", ""), "raw": result.get("body", "")[:400]}
    return {"ok": False, "status": last.get("status"),
            "error": last.get("error", "model not found"),
            "raw": last.get("body", "")[:400]}


def transcribe(wav_path: Path) -> int:
    if not wav_path.exists():
        print(json.dumps({"ok": False, "error": "missing wav", "path": str(wav_path)}))
        return 3
    try:
        audio = _read_audio(wav_path)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 3
    api_key = _load_api_key()
    if not api_key:
        print(json.dumps({"ok": False, "error": "gemini api key missing"}))
        return 2

    audio_b64 = base64.b64encode(audio).decode("ascii")
    mime = _mime_for(wav_path)
    started = time.time()
    result = _call_with_fallback(audio_b64, mime, TRANSCRIBE_PROMPT)
    elapsed = time.time() - started

    if not result.get("ok"):
        status = result.get("status") or 0
        if 400 <= status < 500:
            code = 4
        elif status >= 500:
            code = 5
        elif status == 0:
            code = 6
        else:
            code = 7
        print(json.dumps({"ok": False, "error": result.get("error", "unknown"),
                          "status": status, "elapsed_s": round(elapsed, 2)}))
        return code

    response = result.get("response") or {}
    text, finish = _extract_text(response)
    text = (text or "").strip()
    if not text or finish in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
        print(json.dumps({"ok": False, "error": "empty or blocked", "finish": finish,
                          "elapsed_s": round(elapsed, 2)}))
        return 8 if finish else 7
    print(text)
    return 0


def confirm_pedro(wav_path: Path) -> int:
    if not wav_path.exists():
        print(json.dumps({"ok": False, "error": "missing wav"}))
        return 3
    try:
        audio = _read_audio(wav_path)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 3
    if not _load_api_key():
        print(json.dumps({"ok": False, "error": "gemini api key missing"}))
        return 2

    audio_b64 = base64.b64encode(audio).decode("ascii")
    mime = _mime_for(wav_path)
    result = _call_with_fallback(audio_b64, mime, CONFIRM_PROMPT)
    if not result.get("ok"):
        print(json.dumps({"ok": False, "error": result.get("error", "unknown")}))
        return 6
    text, _ = _extract_text(result.get("response") or {})
    text = (text or "").strip().upper()
    yes = text == "YES"
    print(json.dumps({"ok": True, "yes": yes, "raw": text}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_t = sub.add_parser("transcribe", help="transcribe full command from WAV")
    p_t.add_argument("wav", type=Path)
    p_c = sub.add_parser("confirm_pedro", help="YES/NO gate for the wake phrase")
    p_c.add_argument("wav", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "transcribe":
        return transcribe(args.wav)
    if args.cmd == "confirm_pedro":
        return confirm_pedro(args.wav)
    parser.error("unknown subcommand")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
