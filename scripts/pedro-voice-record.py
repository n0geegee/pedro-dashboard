#!/usr/bin/env python3
"""Pedro voice — ALSA capture helper.

Captures a single short utterance (default 4 s) from the configured ALSA
device into a 16 kHz / 16-bit / mono WAV file. Returns the path to the WAV
and basic stats. Failures are explicit; this script never returns success
on a partial or empty capture.

Usage:
    python3 scripts/pedro-voice-record.py --duration 4 --out /tmp/pedro.wav
    python3 scripts/pedro-voice-record.py --device plughw:0,0 --duration 3
    python3 scripts/pedro-voice-record.py --probe   # 1 s silence probe, prints stats, exits 0/2

Exit codes:
    0  success (WAV written, RMS > silence threshold)
    2  success but silence (RMS < threshold); caller decides if it is an error
    3  arecord missing
    4  arecord non-zero exit
    5  WAV too small / corrupt
    6  device busy / not configured
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

DEFAULT_DEVICE = "plughw:0,0"
DEFAULT_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH = 2  # 16-bit
SILENCE_RMS_THRESHOLD = 200.0  # empirical for 16-bit PCM; below this = silence


def _which_arecord() -> str:
    p = shutil.which("arecord")
    if not p:
        return ""
    return p


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        f.write("\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def _wav_stats(path: Path) -> dict:
    if not path.exists() or path.stat().st_size < 44:
        return {"ok": False, "reason": "missing or too small"}
    try:
        with wave.open(str(path), "rb") as wf:
            nframes = wf.getnframes()
            fr = wf.getframerate()
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            if fr != DEFAULT_RATE or ch != DEFAULT_CHANNELS or sw != DEFAULT_SAMPLE_WIDTH:
                return {
                    "ok": False,
                    "reason": f"unexpected WAV format: rate={fr} ch={ch} sw={sw}",
                    "size": path.stat().st_size,
                }
            raw = wf.readframes(nframes)
    except (wave.Error, EOFError) as exc:
        return {"ok": False, "reason": f"wave error: {exc}", "size": path.stat().st_size}

    if not raw:
        return {"ok": False, "reason": "empty frames", "size": path.stat().st_size}

    # RMS over 16-bit signed little-endian samples
    n = len(raw) // 2
    if n == 0:
        return {"ok": False, "reason": "no samples", "size": path.stat().st_size}
    samples = struct.unpack(f"<{n}h", raw)
    sq_sum = 0
    peak = 0
    for s in samples:
        v = int(s)
        sq_sum += v * v
        if abs(v) > peak:
            peak = abs(v)
    rms = (sq_sum / n) ** 0.5
    return {
        "ok": True,
        "size": path.stat().st_size,
        "frames": nframes,
        "duration_s": nframes / fr,
        "rms": round(rms, 2),
        "peak": peak,
        "silent": rms < SILENCE_RMS_THRESHOLD,
    }


def capture(device: str, duration: float, out_path: Path, rate: int = DEFAULT_RATE,
            channels: int = DEFAULT_CHANNELS) -> int:
    arecord = _which_arecord()
    if not arecord:
        print(json.dumps({"ok": False, "error": "arecord missing"}), file=sys.stderr)
        return 3

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        arecord,
        "-D", device,
        "-d", str(int(duration)),
        "-f", "S16_LE",
        "-r", str(rate),
        "-c", str(channels),
        "-q",  # quiet
        str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=duration + 5, check=False)
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "arecord timeout", "device": device}), file=sys.stderr)
        return 4

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")[:400]
        returncode = 4 if "Device or resource busy" in stderr or "busy" in stderr.lower() else 6
        print(json.dumps({"ok": False, "error": stderr.strip() or "arecord failed", "device": device,
                          "returncode": proc.returncode}), file=sys.stderr)
        return returncode

    stats = _wav_stats(out_path)
    if not stats.get("ok"):
        print(json.dumps({"ok": False, "error": stats.get("reason", "bad wav"),
                          "stats": stats, "path": str(out_path)}), file=sys.stderr)
        return 5

    if stats.get("silent"):
        print(json.dumps({"ok": True, "silent": True, "stats": stats,
                          "path": str(out_path), "device": device}))
        return 2

    print(json.dumps({"ok": True, "silent": False, "stats": stats,
                      "path": str(out_path), "device": device}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default=os.environ.get("PEDRO_MIC_DEVICE", DEFAULT_DEVICE))
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE)
    parser.add_argument("--out", default="/tmp/pedro-ptt.wav")
    parser.add_argument("--probe", action="store_true",
                        help="capture 1 s for device probing, print stats, exit 0/2")
    args = parser.parse_args(argv)

    if args.probe:
        return capture(args.device, 1.0, Path(args.out).with_name("pedro-probe.wav"), rate=args.rate)

    return capture(args.device, args.duration, Path(args.out), rate=args.rate)


if __name__ == "__main__":
    raise SystemExit(main())
