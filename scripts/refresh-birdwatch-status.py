#!/usr/bin/env python3
"""Refresh app/state/ll_tbd.json with the Birdwatch LL-card envelope (2026-07-02).

Birdwatch is the calmer replacement of the LL placeholder: a chronological list
of birds recently heard outside (default station "taras"). BirdNET-Go is the
preferred realtime detector, but this probe is tolerant and degraded-by-design:

  * If BirdNET-Go is reachable, we read its SQLite notes or HTTP `/detections`
    endpoint, normalize, and write the live envelope.
  * Else if ``$BIRDWATCH_SOURCE_JSON`` points at a valid JSON file with the
    same shape, we use that (handy for hardware-absent kiosk smoke tests).
  * Else we probe ALSA for an audio capture device (Zoom H4n, USB audio, etc.)
    and report ``audio.status = "missing"`` when none is present, with a calm
    diagnostic line for the dashboard.
  * On any unexpected failure we still write ``status="error"`` so the card
    never goes blank.

Privacy contract (matches the rest of the project):
  * No raw log text, no env values, no secret paths.
  * Detections are filtered by confidence and an in-window cutoff.
  * Station label only, no client-identifying fields.

Usage:
    python3 scripts/refresh-birdwatch-status.py
    python3 scripts/refresh-birdwatch-status.py --ttl 90
    BIRDWATCH_SOURCE_JSON=/path/to/fixture.json python3 scripts/refresh-birdwatch-status.py

Env vars (all optional):
    BIRDWATCH_STATION=taras
    BIRDWATCH_MIN_CONFIDENCE=0.70
    BIRDWATCH_WINDOW_MINUTES=20
    BIRDWATCH_MAX_ROWS=7
    BIRDWATCH_SOURCE_JSON=/path/to/file.json
    BIRDNET_GO_DB=/path/to/birdnet.db
    BIRDNET_GO_HTTP=http://127.0.0.1:8080/  (BirdNET-Go web UI root)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import (  # noqa: E402
    atomic_write,
    envelope,
    now_iso,
    resolve_state_dir,
    safe_float,
    write_error_envelope,
)

WIDGET = "ll_tbd"
DEFAULT_TTL = 90
HTTP_TIMEOUT_S = 2.0
MAX_DETECTIONS = 200  # absolute cap before filtering — protects against huge DBs

WARSAW_TZ = ZoneInfo("Europe/Warsaw")

POLISH_COMMON_HINTS = {
    # Lightweight fallback: scientific/genus hint -> common Polish name.
    # BirdNET-Go usually returns English common + scientific; we map a few
    # of the most common Polish feeder/garden species to a calm PL label.
    "Turdus merula": "Kos",
    "Turdus philomelos": "Śpiewak",
    "Erithacus rubecula": "Rudzik",
    "Parus major": "Bogatka",
    "Cyanistes caeruleus": "Modraszka",
    "Passer domesticus": "Wróbel",
    "Passer montanus": "Mazurek",
    "Sturnus vulgaris": "Szpak",
    "Fringilla coelebs": "Zięba",
    "Carduelis carduelis": "Szczygieł",
    "Serinus serinus": "Kulczyk",
    "Chloris chloris": "Dzwoniec",
    "Pica pica": "Sroka",
    "Garrulus glandarius": "Sójka",
    "Corvus corax": "Kruk",
    "Corvus corone": "Kawka",
    "Corvus monedula": "Kawka",
    "Columba palumbus": "Grzywacz",
    "Streptopelia decaocto": "Sierpówka",
    "Phoenicurus ochruros": "Kopciuszek",
    "Phoenicurus phoenicurus": "Pleszka",
    "Motacilla alba": "Pliszka siwa",
    "Hirundo rustica": "Dymówka",
    "Delichon urbicum": "Oknówka",
    "Apus apus": "Jerzyk",
    "Dendrocopos major": "Dzięcioł duży",
}


# ---------------------------------------------------------------------------
# env helpers
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_iso_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _format_warsaw_label(value: Any) -> str:
    """Render an ISO UTC timestamp as ``HH:MM:SS`` (or ``HH:MM``) in Warsaw."""
    ts = _parse_iso_utc(value)
    if ts is None:
        return "--:--"
    local = ts.astimezone(WARSAW_TZ)
    if local.second:
        return local.strftime("%H:%M:%S")
    return local.strftime("%H:%M")


def _polish_common(scientific: Any, english_common: Any) -> str | None:
    """Return a Polish common name when we have a confident mapping."""
    if isinstance(scientific, str):
        h = POLISH_COMMON_HINTS.get(scientific.strip())
        if h:
            return h
    # Fallback for unknown species: keep BirdNET's English label (still useful,
    # never leaking a secret). Renderer shows it lower-case.
    if isinstance(english_common, str):
        low = english_common.strip()
        if low:
            return low
    return None


# ---------------------------------------------------------------------------
# audio device probe (H4n / USB audio)
# ---------------------------------------------------------------------------


def _probe_audio_device(station: str) -> dict:
    """Cheap ALSA probe — does the system see a capture card we can use?

    We deliberately do not record anything here: this only checks whether a
    capture device is wired up. Recording 20s of silence just to detect "no
    card" would waste I/O and could fail noisily on the kiosk.
    """
    arecord = shutil.which("arecord")
    if not arecord:
        return {
            "status": "unknown",
            "device": None,
            "sample_rate": None,
            "last_audio_at": None,
            "message": "Brak arecord — nie można zweryfikować karty audio.",
        }
    try:
        out = subprocess.run(
            [arecord, "-l"], capture_output=True, text=True, timeout=2.0, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return {
            "status": "unknown",
            "device": None,
            "sample_rate": None,
            "last_audio_at": None,
            "message": "arecord nie odpowiedział.",
        }
    text = (out.stdout or "") + (out.stderr or "")
    # ALSA prints "card N: <Name>, device M: <Device>" per capture device.
    if "card" not in text.lower() or "device" not in text.lower():
        return {
            "status": "missing",
            "device": None,
            "sample_rate": None,
            "last_audio_at": None,
            "message": f"Podłącz Zoom H4n w trybie USB Audio I/F (stacja: {station}).",
        }
    # Pick the first labelled capture card from the listing.
    label = None
    for line in text.splitlines():
        if "card" in line and "device" in line:
            # Example: "card 1: H4n [Zoom H4n], device 0: USB Audio [USB Audio]"
            after_card = line.split(":", 1)[1].strip() if ":" in line else line
            label = after_card.split("]", 1)[0].strip(" [")
            if label:
                break
    return {
        "status": "ok",
        "device": label or "nieznana karta audio",
        "sample_rate": 44100,  # H4n default; BirdNET-Go re-samples internally.
        "last_audio_at": None,
        "message": None,
    }


# ---------------------------------------------------------------------------
# source adapters
# ---------------------------------------------------------------------------


def _read_fixture(path: Path) -> list[dict]:
    """Read detections from a JSON file (BIRDWATCH_SOURCE_JSON or test fixture).

    Expected schema (top-level dict with ``detections`` list, or a bare list):
        {
          "detections": [
            {"heard_at": "ISO UTC",
             "scientific": "Turdus merula",
             "common_en": "Common Blackbird",
             "confidence": 0.86,
             "station": "taras",
             "source": "birdnet"},
             ...
          ]
        }
    """
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("detections", "notes", "results"):
            v = data.get(key)
            if isinstance(v, list):
                items = v
                break
        else:
            items = []
    else:
        items = []
    return [i for i in items if isinstance(i, dict)]


def _read_birdnet_db(db_path: Path, since: datetime) -> list[dict]:
    """Read notes from a BirdNET-Go SQLite database.

    BirdNET-Go's default schema (post-1.0) is ``note`` table with at least:
        Date, Time, ScientificName, CommonName, Confidence, SpeciesCode, ...
    Older builds used a different column set; we tolerate both.
    """
    detections: list[dict] = []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0].lower() for row in cur.fetchall()}
    finally:
        conn.close()
    if not tables:
        return detections
    table = "note" if "note" in tables else next(iter(tables))
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    try:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?",
                (MAX_DETECTIONS,),
            )
        except sqlite3.Error:
            return detections
        cols = {
            str(description[0]).lower()
            for description in (cur.description or ())
        }
        for row in cur.fetchall():
            d = dict(row)
            heard_at = _combine_birdnet_timestamp(d, cols)
            if heard_at is None:
                continue
            if heard_at < since:
                continue
            detections.append(
                {
                    "heard_at": heard_at.isoformat(timespec="seconds").replace(
                        "+00:00", "Z"
                    ),
                    "scientific": _field(d, "scientificname") or _field(d, "scientific_name"),
                    "common_en": _field(d, "commonname") or _field(d, "common_name"),
                    "confidence": _confidence_to_float(
                        _field(d, "confidence")
                    ),
                    "station": _field(d, "station") or "taras",
                    "source": "birdnet",
                }
            )
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return detections


def _confidence_to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # BirdNET-Go stores either 0..1 or 0..100. Normalize to 0..1.
    if f > 1.0:
        f = f / 100.0
    return max(0.0, min(1.0, f))


def _field(d: dict, name: str) -> Any:
    """Read a SQLite row field without depending on column capitalization."""
    wanted = name.lower()
    for key, value in d.items():
        if str(key).lower() == wanted:
            return value
    return None


def _combine_birdnet_timestamp(d: dict, cols: set[str]) -> datetime | None:
    """Best-effort timestamp for BirdNET-Go ``note`` rows.

    Newer builds: separate ``Date`` and ``Time`` columns ("YYYY-MM-DD HH:MM:SS").
    Older builds: ``Date`` (UNIX epoch seconds) or ``Time`` (epoch).
    """
    if "date" in cols:
        raw = _field(d, "date")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(raw, str) and raw:
            raw = raw.strip()
            # BirdNET-Go commonly stores calendar date and clock time separately.
            raw_time = _field(d, "time") if "time" in cols else None
            if isinstance(raw_time, str) and raw_time.strip():
                for candidate in (f"{raw}T{raw_time.strip()}", f"{raw} {raw_time.strip()}"):
                    ts = _parse_iso_utc(candidate)
                    if ts:
                        return ts
            # ISO 8601 or a combined date/time string.
            ts = _parse_iso_utc(raw)
            if ts and ("T" in raw or " " in raw):
                return ts
            # Date-only — assume noon UTC.
            try:
                dt = datetime.strptime(raw[:10], "%Y-%m-%d").replace(
                    hour=12, tzinfo=timezone.utc
                )
                return dt
            except ValueError:
                return None
    if "time" in cols:
        raw = _field(d, "time")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(raw, str):
            return _parse_iso_utc(raw)
    return None


def _fetch_birdnet_http(base: str, since: datetime) -> list[dict]:
    """Try BirdNET-Go's HTTP detector endpoint. Best-effort only."""
    url = base.rstrip("/") + "/v1/detections"
    qs = f"?since={since.isoformat().replace('+00:00', 'Z')}"
    try:
        req = urllib.request.Request(
            url + qs,
            headers={"Accept": "application/json", "User-Agent": "PedroDashboard/1.4"},
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            raw = resp.read(64 * 1024)
        data = json.loads(raw.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return []
    if isinstance(data, dict):
        for key in ("detections", "notes", "results"):
            v = data.get(key)
            if isinstance(v, list):
                return [i for i in v if isinstance(i, dict)]
        return []
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    return []


def _gather_detections(
    station: str,
    since: datetime,
) -> tuple[list[dict], str]:
    """Return ``(detections, source_label)`` from the first adapter that yields data.

    Adapters tried in order:
      1. ``BIRDWATCH_SOURCE_JSON`` — JSON fixture (tests + manual smoke).
      2. ``BIRDNET_GO_DB`` — SQLite (preferred for live detectors).
      3. ``BIRDNET_GO_HTTP`` — BirdNET-Go HTTP endpoint.
    Empty list with source "none" means no adapter was usable.
    """
    src = os.environ.get("BIRDWATCH_SOURCE_JSON", "").strip()
    if src:
        path = Path(src).expanduser()
        if path.is_file():
            try:
                items = _read_fixture(path)
                if items:
                    return items, "fixture"
            except (OSError, ValueError):
                pass
    db = os.environ.get("BIRDNET_GO_DB", "").strip()
    if db:
        path = Path(db).expanduser()
        if path.is_file():
            try:
                items = _read_birdnet_db(path, since)
                if items:
                    return items, "birdnet-go-db"
            except (OSError, sqlite3.Error):
                pass
    http = os.environ.get("BIRDNET_GO_HTTP", "").strip()
    if http:
        items = _fetch_birdnet_http(http, since)
        if items:
            return items, "birdnet-go-http"
    return [], "none"


# ---------------------------------------------------------------------------
# normalization & filtering
# ---------------------------------------------------------------------------


def _normalize(items: list[dict], since: datetime, station: str) -> list[dict]:
    """Normalize raw adapter rows into the dashboard detections shape."""
    out: list[dict] = []
    now_utc = datetime.now(timezone.utc)
    for raw in items:
        heard_at = _parse_iso_utc(
            raw.get("heard_at") or raw.get("time") or raw.get("Date")
        )
        if heard_at is None:
            continue
        conf = safe_float(raw.get("confidence"), -1.0)
        if conf < 0:
            continue
        if heard_at < since:
            continue
        scientific = raw.get("scientific") or raw.get("ScientificName") or ""
        common_en = raw.get("common_en") or raw.get("CommonName") or ""
        detected_station = raw.get("station") or station
        sid = (
            raw.get("id")
            or f"{heard_at.strftime('%Y%m%dT%H%M%SZ')}-{detected_station}-"
            f"{''.join(ch for ch in str(scientific).lower().replace(' ', '-') if ch.isalnum() or ch == '-')[:40]}"
        )
        time_label = _format_warsaw_label(heard_at.isoformat())
        out.append(
            {
                "id": sid,
                "heard_at": heard_at.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "time_label": time_label,
                "species_pl": _polish_common(scientific, common_en),
                "species_en": common_en if isinstance(common_en, str) else "",
                "scientific": scientific if isinstance(scientific, str) else "",
                "confidence": round(conf, 3),
                "confidence_label": f"{int(round(conf * 100))}%",
                "station": detected_station,
                "source": raw.get("source") or "birdwatch",
                "clip_path": raw.get("clip_path"),
                "fresh": (now_utc - heard_at).total_seconds() < 300,
            }
        )
    out.sort(key=lambda d: d["heard_at"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


def probe() -> dict:
    station = os.environ.get("BIRDWATCH_STATION", "taras").strip() or "taras"
    min_conf = max(0.0, min(1.0, _env_float("BIRDWATCH_MIN_CONFIDENCE", 0.70)))
    window_minutes = max(1, min(240, _env_int("BIRDWATCH_WINDOW_MINUTES", 20)))
    max_rows = max(1, min(20, _env_int("BIRDWATCH_MAX_ROWS", 7)))

    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    raw_items, source_label = _gather_detections(station, since)
    all_items = _normalize(raw_items, since, station)
    detections = [d for d in all_items if d["confidence"] >= min_conf][:max_rows]

    audio = _probe_audio_device(station)
    if not detections and source_label == "none":
        audio["last_audio_at"] = None

    empty_msg = (
        "Cisza albo brak pewnego rozpoznania w ostatnich "
        f"{window_minutes} min (próg {int(round(min_conf * 100))}%)."
    )

    return {
        "kind": "birdwatch",
        "title": "PTAKI ZA OKNEM",
        "subtitle": "Nasłuch tarasu — BirdNET / H4n",
        "station": station,
        "audio": audio,
        "detections": detections,
        "detection_count_total": len(all_items),
        "min_confidence": min_conf,
        "window_minutes": window_minutes,
        "source": source_label,
        "empty_message": empty_msg,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Refresh app/state/ll_tbd.json with the Birdwatch LL-card envelope."
    )
    p.add_argument("--out", default=None,
                   help="output state directory (default: app/state/ next to project root)")
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL,
                   help=f"ttl_seconds written into the envelope (default: {DEFAULT_TTL})")
    args = p.parse_args(argv)

    state_dir = resolve_state_dir(args.out)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / f"{WIDGET}.json"

    try:
        data = probe()
        # Success path is always status=ok from the dashboard's perspective:
        # `audio.status` carries the microphone state separately.
        payload = envelope(WIDGET, "ok", args.ttl, data)
        atomic_write(out_path, payload)
        print(
            f"wrote {out_path} "
            f"(kind=birdwatch source={data['source']} "
            f"audio={data['audio']['status']} rows={len(data['detections'])} "
            f"total={data['detection_count_total']})"
        )
        return 0
    except Exception as exc:  # last-ditch: never leave the card blank
        code = "BIRDWATCH_PROBE_INTERNAL_ERROR"
        write_error_envelope(
            state_dir, WIDGET, args.ttl, code,
            "Birdwatch probe failed; LL card przełączony w tryb diagnostyczny.",
        )
        log_dir = state_dir.parent / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "refresh-birdwatch-status.err.log").open(
                "a", encoding="utf-8"
            ) as f:
                f.write(f"[{now_iso()}] {code}: {exc!r}\n")
        except OSError:
            pass
        print(f"wrote {out_path} (status=error) and logged traceback", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
