#!/usr/bin/env python3
"""Pedro voice — local TTS via espeak-ng.

Speaks a Polish summary over the default ALSA sink. Sanitised (no secrets,
no raw paths, length cap). Exit codes follow the design doc §11.

Usage:
    python3 scripts/pedro-voice-tts.py "Cześć, jestem Pedro"
    PEDRO_VOICE_SPEAK=off python3 scripts/pedro-voice-tts.py "skip me"
    echo "Wynik: 18 stopni" | python3 scripts/pedro-voice-tts.py -

Exit codes:
    0  spoken (or silent skip on PEDRO_VOICE_SPEAK=off)
    1  sanitisation emptied the text
    2  espeak-ng missing
    3  espeak-ng non-zero exit
    4  input text too long after sanitisation
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

MAX_LEN = 400
DEFAULT_VOICE = "pl"
DEFAULT_RATE = 165
DEFAULT_PITCH = 50

SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|bearer)\b\s*[:=]?\s*\S+"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b[A-Za-z0-9_=-]{32,}\b"),
]


def _redact(text: str) -> str:
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub("[redacted]", out)
    return out


def _sanitise(text: str) -> str:
    text = _redact(text)
    # Strip control characters; collapse whitespace
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    if len(text) > MAX_LEN:
        text = text[: MAX_LEN - 3] + "..."
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text", nargs="?",
                        help="text to speak; pass '-' to read from stdin")
    parser.add_argument("--voice", default=os.environ.get("PEDRO_TTS_VOICE", DEFAULT_VOICE))
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE)
    parser.add_argument("--pitch", type=int, default=DEFAULT_PITCH)
    parser.add_argument("--dry-run", action="store_true",
                        help="print sanitised text and exit 0; do not call espeak-ng")
    args = parser.parse_args(argv)

    if args.text == "-" or (args.text is None and not sys.stdin.isatty()):
        text = sys.stdin.read()
    elif args.text is None:
        parser.error("text argument required (or pipe via '-' / stdin)")
        return 2
    else:
        text = args.text

    sanitised = _sanitise(text)
    if not sanitised:
        print(json_dumps({"ok": False, "error": "empty after sanitisation", "input_len": len(text)}))
        return 1
    if len(sanitised) > MAX_LEN:
        print(json_dumps({"ok": False, "error": "too long", "len": len(sanitised)}))
        return 4

    if args.dry_run:
        print(sanitised)
        return 0

    if os.environ.get("PEDRO_VOICE_SPEAK", "on").lower() in ("off", "0", "false", "no"):
        print(json_dumps({"ok": True, "skipped": "PEDRO_VOICE_SPEAK=off", "text": sanitised}))
        return 0

    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary:
        print(json_dumps({"ok": False, "error": "espeak-ng missing", "text": sanitised}))
        return 2

    cmd = [binary, "-v", args.voice, "-s", str(args.rate), "-p", str(args.pitch), sanitised]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
    except subprocess.TimeoutExpired:
        print(json_dumps({"ok": False, "error": "espeak-ng timeout", "text": sanitised}))
        return 3

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")[:200]
        print(json_dumps({"ok": False, "error": stderr.strip() or "espeak-ng failed",
                          "returncode": proc.returncode, "text": sanitised}))
        return 3

    print(json_dumps({"ok": True, "spoke": sanitised}))
    return 0


def json_dumps(obj: dict) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
