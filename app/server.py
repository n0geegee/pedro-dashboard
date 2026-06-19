#!/usr/bin/env python3
"""Pedro Dashboard — Etap 1 lightweight static MVP server.

Python stdlib only. Bind default 127.0.0.1:17890.

Endpoints:
- GET /                  -> serves static index.html
- GET /static/<path>     -> serves static assets (CSS/JS)
- GET /api/health        -> dashboard self-health JSON
- GET /api/state         -> aggregated mock state (dashboard/system/hermes/openviking/
                            current_focus/alerts/decisions/voice_console)
- GET /api/voice_console -> Pedro Voice Console state only

Privacy: this is the MVP. Backend does not yet redact; mock state contains no
secrets, raw logs, or private content. Privacy enforcement is added in Etap 5.

All state files are loaded with tolerant JSON parse: malformed files return
status="error" but never crash the server.
"""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import socketserver  # noqa: F401  (kept for stdlib parity with plan)
import sys
import threading
import time
from datetime import datetime, time as dtime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

WARSAW_TZ = ZoneInfo("Europe/Warsaw")
_PLACEHOLDER_PL_MATCHDAY = "{{pl_matchday}}"
_BODY_TAG_RE = re.compile(
    r"<body\b([^>]*)>",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17890
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
STATE_DIR = APP_DIR / "state"
LOGS_DIR = APP_DIR / "logs"

# Env overrides (kept simple for Etap 1). Keep MVP loopback-only by default and
# refuse accidental LAN exposure; explicit LAN support is a future decision.
_requested_host = os.environ.get("DASHBOARD_HOST", DEFAULT_HOST)
HOST = _requested_host if _requested_host in ("127.0.0.1", "localhost") else DEFAULT_HOST
PORT = int(os.environ.get("DASHBOARD_PORT", str(DEFAULT_PORT)))
PRIVACY_MODE = os.environ.get("DASHBOARD_PRIVACY_MODE", "private")  # MVP default

SERVER_STARTED_AT = time.time()
SERVER_STARTED_ISO = datetime.now(timezone.utc).isoformat(timespec="seconds")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOGS_DIR / "server.log"

logging.basicConfig(
    level=os.environ.get("DASHBOARD_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("pedro_dashboard")


# ---------------------------------------------------------------------------
# State loading
# ---------------------------------------------------------------------------

# Map of logical state name -> file in app/state/. Each file may be missing or
# malformed; load_state() always returns a valid widget envelope.
STATE_FILES: Dict[str, str] = {
    "dashboard": "dashboard.json",
    "system": "system.json",
    "hermes": "hermes.json",
    "openviking": "openviking.json",
    "current_focus": "current_focus.json",
    "alerts": "alerts.json",
    "decisions": "decisions.json",
    "voice_console": "voice_console.json",
    # Three-zone media dashboard widgets (visual v1)
    "weather": "weather.json",
    "route": "route.json",
    "calendar": "calendar.json",
    "volleyball": "volleyball.json",
    "media": "media.json",
    "ll_tbd": "ll_tbd.json",
    "skin": "skin.json",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_stale(updated_at: Any, ttl_seconds: Any) -> bool:
    """Return True when a state payload is older than its TTL.

    Malformed/missing timestamps are treated as stale if a positive TTL exists.
    """
    try:
        ttl = float(ttl_seconds)
    except (TypeError, ValueError):
        return False
    if ttl <= 0:
        return False
    if not isinstance(updated_at, str) or not updated_at:
        return True
    try:
        stamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
    return age > ttl


def _redact_public_text(value: Any) -> str:
    """Redact secret-looking fragments before JSON reaches the UI."""
    if value is None:
        return ""
    text = str(value)
    patterns = [
        r"(?i)\b(api[_-]?key|token|secret|password|passwd|bearer)\b\s*[:=]?\s*\S+",
        r"(?i)\b(sk-[A-Za-z0-9_-]{16,})\b",
        r"\b[A-Za-z0-9_=-]{32,}\b",
    ]
    for pat in patterns:
        text = re.sub(pat, "[redacted]", text)
    return text


def _privacy_filter_voice(out: Dict[str, Any]) -> Dict[str, Any]:
    # Runtime privacy is trusted; JSON files are mutable state and must not be
    # able to downgrade `DASHBOARD_PRIVACY_MODE=private|guest` to `normal`.
    mode = PRIVACY_MODE
    out["privacy_mode"] = mode
    utterance = dict(out.get("utterance") or {})
    result = dict(out.get("result") or {})
    voice = dict(out.get("voice") or {})
    if mode == "guest":
        voice["state"] = "privacy_blocked"
        voice["mode"] = "disabled"
        utterance["partial"] = ""
        utterance["final"] = ""
        result["summary"] = "Treść ukryta w trybie guest."
        result["clarifying_question"] = None
        result["requires_user_action"] = False
    elif mode == "private":
        utterance["partial"] = ""
        utterance["final"] = ""
        if result.get("summary"):
            result["summary"] = "Wynik ukryty w trybie private."
        result["clarifying_question"] = None
        result["requires_user_action"] = False
    else:
        utterance["partial"] = _redact_public_text(utterance.get("partial"))
        utterance["final"] = _redact_public_text(utterance.get("final"))
        result["summary"] = _redact_public_text(result.get("summary"))
        result["clarifying_question"] = _redact_public_text(result.get("clarifying_question"))
    out["voice"] = voice
    out["utterance"] = utterance
    out["result"] = result
    return out


def _empty_envelope(name: str, status: str = "empty", error: str = None) -> Dict[str, Any]:
    return {
        "status": status,
        "updated_at": None,
        "ttl_seconds": None,
        "privacy_mode": PRIVACY_MODE,
        "data": {},
        "error": error,
        "_widget": name,
    }


def _read_json(path: Path) -> Tuple[bool, Any, str]:
    """Tolerant JSON read. Returns (ok, payload, error_message)."""
    if not path.exists():
        return False, None, f"missing:{path.name}"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        return False, None, f"json_decode_error:{exc.msg}@line{exc.lineno}"
    except OSError as exc:
        return False, None, f"io_error:{exc.strerror or exc}"
    return True, data, None


def _load_minimax_usage() -> Dict[str, Any]:
    """Load MiniMax token-usage JSON from the agent.log sniffer.
    Returns a compact envelope: 5h window + all-time + last-session.
    Standalone endpoint only — not exposed via /api/state widgets, so the
    kiosk UI is unaffected. Use /api/minimax_usage to read.
    """
    path = Path("/home/imac-hermes/.local/state/hermes/minimax-usage.json")
    if not path.exists():
        return {
            "status": "empty",
            "updated_at": None,
            "data": {
                "five_h_in": 0, "five_h_out": 0, "five_h_request_count": 0,
                "all_time_in": 0, "all_time_out": 0, "all_time_request_count": 0,
                "all_time_session_count": 0,
                "sessions": [],
            },
        }
    try:
        raw = json.loads(path.read_text())
    except Exception as exc:
        return {"status": "error", "error": f"parse:{exc}", "data": {}}
    sessions = raw.get("sessions", {})
    top_items = sorted(sessions.items(), key=lambda kv: kv[1].get("last_seen", 0), reverse=True)[:5]
    return {
        "status": "ok",
        "updated_at": raw.get("updated_at"),
        "data": {
            "five_h_in": raw.get("five_h_in", 0),
            "five_h_out": raw.get("five_h_out", 0),
            "five_h_request_count": raw.get("five_h_request_count", 0),
            "five_h_window_first": raw.get("five_h_window_first", 0),
            "all_time_in": raw.get("all_time_in", 0),
            "all_time_out": raw.get("all_time_out", 0),
            "all_time_cache_read": raw.get("all_time_cache_read", 0),
            "all_time_request_count": raw.get("all_time_request_count", 0),
            "all_time_session_count": raw.get("all_time_session_count", 0),
            "last_sessions": [
                {
                    "id": sid[:26],
                    "request_count": s.get("request_count", 0),
                    "in_total": s.get("in_total", 0),
                    "out_total": s.get("out_total", 0),
                    "last_in": s.get("last_in", 0),
                    "last_cache_pct": s.get("last_cache_pct", 0),
                    "last_seen": s.get("last_seen", 0),
                }
                for sid, s in top_items
            ],
        },
    }


def load_widget(name: str) -> Dict[str, Any]:
    """Load a single widget state, normalizing to the envelope contract.

    For most widgets, the JSON file holds a flat envelope with a `data` field.
    For `voice_console`, the file follows the Pedro Voice Console contract from
    docs/03_voice_console_contract.md: top-level fields `voice`, `utterance`,
    `activity`, `result`, `error` live next to envelope fields. We preserve
    that contract verbatim and only sanitize the envelope-level fields.
    """
    fname = STATE_FILES.get(name)
    if fname is None:
        return _empty_envelope(name, status="error", error=f"unknown_widget:{name}")
    ok, payload, err = _read_json(STATE_DIR / fname)
    if not ok:
        # Distinguish missing (empty) vs broken (error)
        status = "empty" if err and err.startswith("missing:") else "error"
        return _empty_envelope(name, status=status, error=err)
    if not isinstance(payload, dict):
        return _empty_envelope(name, status="error", error="payload_not_object")

    raw_status = payload.get("status", "ok")
    status = raw_status if raw_status in ("ok", "stale", "error", "empty", "disabled") else "ok"
    if status == "ok" and _is_stale(payload.get("updated_at"), payload.get("ttl_seconds")):
        status = "stale"

    if name == "voice_console":
        # Voice Console keeps its own top-level contract; just sanitize the
        # envelope fields and tag the widget.
        out: Dict[str, Any] = {
            "status": status,
            "updated_at": payload.get("updated_at"),
            "ttl_seconds": payload.get("ttl_seconds"),
            "privacy_mode": payload.get("privacy_mode", PRIVACY_MODE),
            "voice": payload.get("voice", {}),
            "utterance": payload.get("utterance", {}),
            "activity": payload.get("activity", {}),
            "result": payload.get("result", {}),
            "error": payload.get("error", {"code": None, "message_public": None, "debug_ref": None}),
            "_widget": name,
        }
        return _privacy_filter_voice(out)

    # Default envelope for other widgets
    return {
        "status": status,
        "updated_at": payload.get("updated_at"),
        "ttl_seconds": payload.get("ttl_seconds"),
        "privacy_mode": payload.get("privacy_mode", PRIVACY_MODE),
        "data": payload.get("data", {}),
        "error": payload.get("error"),
        "_widget": name,
    }


def _parse_iso_utc(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp into a timezone-aware datetime (UTC).

    Returns None when the value is missing or malformed. The dashboard stores
    start_at values as ISO-8601 with an explicit offset (typically "+00:00"),
    but we tolerate naive timestamps by assuming UTC.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _poland_match_today(now: datetime | None = None) -> bool:
    """True iff volleyball.json has any Poland match whose start_at (UTC) lands
    in the current local Warsaw day window (00:00-23:59 Europe/Warsaw).

    Scans both volleyball.men and volleyball.women for a match where either
    home.flag == "pl" or away.flag == "pl". The scan is tolerant of missing
    or malformed state files — a missing volleyball.json simply yields False.
    """
    widget = load_widget("volleyball")
    data = widget.get("data") if isinstance(widget, dict) else None
    if not isinstance(data, dict):
        return False
    groups: List[List[Dict[str, Any]]] = []
    for key in ("men", "women"):
        group = data.get(key)
        if isinstance(group, list):
            groups.append(group)
    if not groups:
        return False
    if now is None:
        now = datetime.now(WARSAW_TZ)
    else:
        now = now.astimezone(WARSAW_TZ)
    day_start = datetime.combine(now.date(), dtime.min, tzinfo=WARSAW_TZ)
    day_end = datetime.combine(now.date(), dtime.max, tzinfo=WARSAW_TZ)
    for group in groups:
        for match in group:
            if not isinstance(match, dict):
                continue
            home = match.get("home") or {}
            away = match.get("away") or {}
            is_poland = (
                (isinstance(home, dict) and home.get("flag") == "pl")
                or (isinstance(away, dict) and away.get("flag") == "pl")
            )
            if not is_poland:
                continue
            stamp = _parse_iso_utc(match.get("start_at"))
            if stamp is None:
                continue
            local_stamp = stamp.astimezone(WARSAW_TZ)
            if day_start <= local_stamp <= day_end:
                return True
    return False


def _render_index_html(raw_html: str) -> str:
    """Inject the server-computed body attributes into the static index.html.

    The static template carries a {{pl_matchday}} placeholder in the <body>
    tag. We replace it with a real "1" or "0" based on the volleyball widget
    state. If the placeholder is missing (older template), we fall back to a
    regex-based injection on the <body> tag.
    """
    flag = "1" if _poland_match_today() else "0"
    if _PLACEHOLDER_PL_MATCHDAY in raw_html:
        return raw_html.replace(_PLACEHOLDER_PL_MATCHDAY, flag, 1)

    def _inject(match: "re.Match[str]") -> str:
        attrs = match.group(1) or ""
        # Strip any prior data-pl-matchday so we don't double-attribute.
        attrs = re.sub(
            r'\s+data-pl-matchday\s*=\s*"[^"]*"',
            "",
            attrs,
        )
        return f"<body{attrs} data-pl-matchday=\"{flag}\">"

    rendered = _BODY_TAG_RE.sub(_inject, raw_html, count=1)
    return rendered


def load_aggregated_state() -> Dict[str, Any]:
    widgets = {name: load_widget(name) for name in STATE_FILES}
    # Top-level status: error if any error; stale if any stale; ok otherwise
    statuses = {w["status"] for w in widgets.values()}
    if "error" in statuses:
        overall = "error"
    elif "stale" in statuses:
        overall = "stale"
    else:
        overall = "ok"
    return {
        "status": overall,
        "updated_at": _now_iso(),
        "privacy_mode": PRIVACY_MODE,
        "server": {
            "started_at": SERVER_STARTED_ISO,
            "uptime_seconds": int(time.time() - SERVER_STARTED_AT),
            "host": HOST,
            "port": PORT,
        },
        # Server-side match-day signal for the PL 50/50 flag. Mirrors the
        # `data-pl-matchday` attribute injected into <body> by _render_index_html.
        # Computed against Europe/Warsaw local-day window (00:00-23:59).
        "poland_match_today": _poland_match_today(),
        "widgets": widgets,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class PedroHandler(BaseHTTPRequestHandler):
    server_version = "PedroDashboard/0.1 (stdlib)"

    # Quieter access log; keep our structured log via the `log` object.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        log.info("%s - %s", self.address_string(), format % args)

    # ---- helpers -----------------------------------------------------------

    def _send_json(self, status: int, payload: Dict[str, Any], *, send_body: bool = True) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _send_file(self, fs_path: Path, content_type: str, *, send_body: bool = True) -> None:
        try:
            data = fs_path.read_bytes()
        except OSError as exc:
            log.warning("static read failed: %s (%s)", fs_path, exc)
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    # ---- routing -----------------------------------------------------------

    def _send_html(self, html_text: str) -> None:
        """Serve a rendered HTML payload (UTF-8). Used for index.html with
        server-injected body attributes such as data-pl-matchday."""
        body = html_text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _route(self, *, send_body: bool) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/" or path == "/index.html":
                if not send_body:
                    # HEAD — send same headers as GET but no body.
                    raw = (STATIC_DIR / "index.html").read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
                try:
                    raw_text = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
                except OSError as exc:
                    log.warning("index.html read failed: %s (%s)", STATIC_DIR / "index.html", exc)
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                self._send_html(_render_index_html(raw_text))
                return
            if path == "/api/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "pedro_dashboard",
                        "version": "0.1.0",
                        "etap": 1,
                        "updated_at": _now_iso(),
                        "uptime_seconds": int(time.time() - SERVER_STARTED_AT),
                        "host": HOST,
                        "port": PORT,
                        "privacy_mode": PRIVACY_MODE,
                    },
                    send_body=send_body,
                )
                return
            if path == "/api/state":
                self._send_json(HTTPStatus.OK, load_aggregated_state(), send_body=send_body)
                return
            if path == "/api/voice_console":
                self._send_json(HTTPStatus.OK, load_widget("voice_console"), send_body=send_body)
                return
            if path == "/api/minimax_usage":
                self._send_json(HTTPStatus.OK, _load_minimax_usage(), send_body=send_body)
                return
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                # Prevent path traversal: resolve and ensure within STATIC_DIR
                candidate = (STATIC_DIR / rel).resolve()
                if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR:
                    self._send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"}, send_body=send_body)
                    return
                if not candidate.is_file():
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=send_body)
                    return
                ctype = self._guess_content_type(candidate.name)
                self._send_file(candidate, ctype, send_body=send_body)
                return
            if path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found", "path": path}, send_body=send_body)
        except Exception:  # pragma: no cover - last-ditch logging
            log.exception("unhandled error in request for %s", self.path)
            try:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal"}, send_body=send_body)
            except Exception:
                pass

    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        self._route(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802 (stdlib API)
        self._route(send_body=False)

    @staticmethod
    def _guess_content_type(name: str) -> str:
        if name.endswith(".html"):
            return "text/html; charset=utf-8"
        if name.endswith(".css"):
            return "text/css; charset=utf-8"
        if name.endswith(".js"):
            return "application/javascript; charset=utf-8"
        if name.endswith(".json"):
            return "application/json; charset=utf-8"
        if name.endswith(".svg"):
            return "image/svg+xml"
        return "application/octet-stream"

    # Reject non-GET for now (MVP)
    def do_POST(self) -> None:  # noqa: N802
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})


# ---------------------------------------------------------------------------
# Server bootstrap
# ---------------------------------------------------------------------------


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _verify_assets() -> None:
    """Lightweight sanity checks for Etap 1 deliverable."""
    expected = [
        STATIC_DIR / "index.html",
        STATIC_DIR / "styles.css",
        STATIC_DIR / "app.js",
    ]
    missing = [str(p) for p in expected if not p.exists()]
    if missing:
        log.warning("missing static files at startup: %s", ", ".join(missing))
    else:
        log.info("static assets present: index.html, styles.css, app.js")
    if not STATE_DIR.exists():
        log.warning("state directory missing: %s", STATE_DIR)
    else:
        n = sum(1 for _ in STATE_DIR.glob("*.json"))
        log.info("state files detected: %d", n)


def install_signal_handlers(server: ReusableThreadingHTTPServer) -> None:
    def _shutdown(signum, _frame):
        log.info("signal %s received, shutting down", signum)
        # shutdown() must be called from another thread when serve_forever is active
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):
            # Not in main thread (e.g. under some test runners); ignore.
            pass


def main() -> int:
    log.info(
        "starting Pedro Dashboard server on http://%s:%d (privacy=%s)",
        HOST, PORT, PRIVACY_MODE,
    )
    _verify_assets()
    try:
        with ReusableThreadingHTTPServer((HOST, PORT), PedroHandler) as srv:
            install_signal_handlers(srv)
            log.info("serving: try http://%s:%d/  and  /api/health", HOST, PORT)
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                log.info("KeyboardInterrupt, shutting down")
    except OSError as exc:
        log.error("failed to bind %s:%d — %s", HOST, PORT, exc)
        return 2
    log.info("server stopped cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
