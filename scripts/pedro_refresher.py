#!/usr/bin/env python3
"""Pedro Dashboard — state refresher (single long-lived scheduler).

Replaces the old "run every probe back to back, then sleep 20s" bash loop.
Each probe is still a separate script run as a subprocess (they need
different interpreters and use SIGALRM timeouts), but now:

  * every probe has its own cadence, so slow network sources (Wikipedia,
    open-meteo, Google Calendar) are not hammered every 20s and never delay
    the fast local probes;
  * every run has a hard timeout, so a hung probe cannot stall the others;
  * a failed probe is retried sooner than its normal cadence;
  * probes that write the same file (media.json: polsat + photos) never run
    at the same time, so their read-modify-write cycles cannot lose updates;
  * the log records only state changes (ok -> failing -> ok), not every tick;
  * a small status file (--status-file) shows the last run of every probe.

Environment (credentials from ~/.hermes/.env, DISPLAY) is prepared by the
bash wrappers, see pedro_load_probe_env in _lifecycle_common.sh.

Usage:
    python3 scripts/pedro_refresher.py                 # run forever
    python3 scripts/pedro_refresher.py --once          # run every probe once
    python3 scripts/pedro_refresher.py --base-interval 20 --status-file F
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from _probe_common import APP_DIR, atomic_write

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = APP_DIR / "state"


def _log(msg: str) -> None:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    print(f"[{stamp}] {msg}", flush=True)


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _python(kind: str) -> Optional[str]:
    """Interpreter for a probe, mirroring the fallbacks the bash loop used."""
    system = os.environ.get("PEDRO_SERVER_CMD", "python3")
    system = shutil.which(system) or "/usr/bin/python3"
    if kind == "hermes":
        hermes = os.environ.get(
            "HERMES_PYTHON", str(Path.home() / ".hermes/hermes-agent/venv/bin/python")
        )
        return hermes if os.access(hermes, os.X_OK) else system
    if kind == "voice":
        voice = os.environ.get("PEDRO_VOICE_PY_BIN", "")
        return voice if voice and os.access(voice, os.X_OK) else None
    return system


def _photos_rotator_alive() -> bool:
    """True when the legacy photos-rotator.sh loop still owns the slideshow."""
    run_dir = os.environ.get("PEDRO_RUN_DIR")
    if not run_dir:
        return False
    try:
        pid = int((Path(run_dir) / "photos-rotator.pid").read_text().strip())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError):
        return False
    return b"photos-rotator.sh" in cmdline


class Probe:
    def __init__(
        self,
        script: str,
        interval: float,
        timeout: float,
        *,
        python: str = "system",
        args: Optional[List[str]] = None,
        lock: Optional[threading.Lock] = None,
        retry: Optional[float] = None,
        skip_if=None,
    ) -> None:
        self.script = script
        self.interval = interval
        self.timeout = timeout
        self.python = python
        self.args = args or []
        self.lock = lock
        self.retry = min(interval, retry if retry is not None else 60.0)
        self.skip_if = skip_if
        # Status, read by the status writer thread.
        self.last_run: Optional[float] = None
        self.last_ok: Optional[float] = None
        self.last_rc: Optional[int] = None
        self.failures = 0
        self.skipped = False


class Refresher:
    def __init__(self, probes: List[Probe], status_file: Optional[Path]) -> None:
        self.probes = [p for p in probes if (SCRIPT_DIR / p.script).is_file()]
        self.status_file = status_file
        self.stop = threading.Event()
        self._children: Dict[int, subprocess.Popen] = {}
        self._children_lock = threading.Lock()
        self.looping = False

    # ---- running one probe -------------------------------------------------

    def run_probe(self, probe: Probe) -> bool:
        if probe.skip_if is not None and probe.skip_if():
            probe.skipped = True
            return True
        probe.skipped = False
        interpreter = _python(probe.python)
        if interpreter is None:
            probe.skipped = True
            return True
        cmd = [interpreter, str(SCRIPT_DIR / probe.script), *probe.args]
        if probe.lock is not None:
            probe.lock.acquire()
        try:
            rc, err_tail = self._spawn(cmd, probe.timeout)
        finally:
            if probe.lock is not None:
                probe.lock.release()
        probe.last_run = time.time()
        probe.last_rc = rc
        if rc == 0:
            if probe.failures:
                _log(f"{probe.script}: recovered after {probe.failures} failed run(s)")
            probe.failures = 0
            probe.last_ok = probe.last_run
            return True
        probe.failures += 1
        if probe.failures == 1 and not self.stop.is_set():
            reason = f"timed out after {probe.timeout:g}s" if rc is None else f"exit {rc}"
            retry = f"; retrying every {probe.retry:g}s" if self.looping else ""
            _log(f"{probe.script}: failing ({reason}){retry}")
            for line in err_tail:
                _log(f"  {probe.script}: {line}")
        return False

    def _spawn(self, cmd: List[str], timeout: float):
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(APP_DIR.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            return 127, [f"spawn failed: {exc}"]
        with self._children_lock:
            self._children[proc.pid] = proc
        try:
            _, err = proc.communicate(timeout=timeout)
            rc: Optional[int] = proc.returncode
        except subprocess.TimeoutExpired:
            self._kill(proc)
            _, err = proc.communicate()
            rc = None
        finally:
            with self._children_lock:
                self._children.pop(proc.pid, None)
        lines = (err or b"").decode("utf-8", "replace").strip().splitlines()
        return rc, lines[-3:]

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        # Probes run in their own session; kill the whole group so helper
        # processes they started (xrandr, curl, ...) go too.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except OSError:
                return
            try:
                proc.wait(timeout=3)
                return
            except subprocess.TimeoutExpired:
                continue

    def kill_children(self) -> None:
        with self._children_lock:
            children = list(self._children.values())
        for proc in children:
            self._kill(proc)

    # ---- scheduling --------------------------------------------------------

    def _probe_loop(self, probe: Probe) -> None:
        while not self.stop.is_set():
            started = time.monotonic()
            ok = self.run_probe(probe)
            delay = probe.interval if ok else probe.retry
            self.stop.wait(max(0.5, delay - (time.monotonic() - started)))

    def _status_loop(self) -> None:
        while not self.stop.wait(15):
            self.write_status()

    def write_status(self) -> None:
        if self.status_file is None:
            return
        payload = {
            "updated_at": _iso(time.time()),
            "pid": os.getpid(),
            "probes": {
                p.script: {
                    "interval_s": p.interval,
                    "last_run": _iso(p.last_run),
                    "last_ok": _iso(p.last_ok),
                    "last_rc": "timeout" if p.last_run and p.last_rc is None else p.last_rc,
                    "consecutive_failures": p.failures,
                    "skipped": p.skipped,
                }
                for p in self.probes
            },
        }
        try:
            atomic_write(self.status_file, payload)
        except OSError as exc:
            _log(f"status file write failed: {exc}")

    def run_once(self) -> int:
        """Mock baseline first, then all live probes in parallel."""
        first, rest = self.probes[:1], self.probes[1:]
        results = [self.run_probe(p) for p in first]
        threads = []
        for probe in rest:
            t = threading.Thread(target=lambda p=probe: results.append(self.run_probe(p)))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        self.write_status()
        return 0 if all(results) else 1

    def run_forever(self) -> int:
        self.looping = True
        _log(
            "refresher started: "
            + ", ".join(f"{p.script.replace('refresh-', '').replace('.py', '')}={p.interval:g}s" for p in self.probes)
        )
        # The mock baseline goes first so a fresh boot never serves missing files.
        if self.probes:
            self.run_probe(self.probes[0])
        self.write_status()
        threads = [threading.Thread(target=self._probe_loop, args=(p,), daemon=True) for p in self.probes]
        threads.append(threading.Thread(target=self._status_loop, daemon=True))
        for t in threads:
            t.start()
        while not self.stop.wait(1):
            pass
        self.kill_children()
        self.write_status()
        _log("refresher stopped")
        return 0


def build_probes(base: float) -> List[Probe]:
    media_lock = threading.Lock()
    live_owned = [
        name
        for name, script in (
            ("system.json", "refresh-system-status.py"),
            ("hermes.json", "refresh-hermes-status.py"),
            ("openviking.json", "refresh-openviking-status.py"),
        )
        if (SCRIPT_DIR / script).is_file()
    ]
    slide = _env_float("PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS", 5)
    return [
        # Must stay first: run_once/run_forever start with the baseline.
        Probe("write-mock-state.py", base, 30, args=["--skip", ",".join(live_owned)]),
        Probe("refresh-system-status.py", base, 30),
        Probe("refresh-hermes-status.py", base, 30),
        Probe("refresh-openviking-status.py", base, 30),
        # Date-based only; set-skin.py re-runs it itself on a manual change.
        Probe("refresh-season-skin.py", _env_float("PEDRO_SKIN_INTERVAL", 300), 30),
        Probe("refresh-weather-status.py", _env_float("PEDRO_WEATHER_INTERVAL", 300), 60),
        # Has its own 5-minute throttle against the Google Routes quota.
        Probe("refresh-route-status.py", _env_float("PEDRO_ROUTE_INTERVAL", 60), 60),
        Probe("refresh-kamila-calendar.py", _env_float("PEDRO_CALENDAR_INTERVAL", 120), 60, python="hermes"),
        Probe("refresh-vnl-volleyball.py", _env_float("PEDRO_VNL_INTERVAL", 300), 60),
        Probe("refresh-polsat-status.py", base, 30, lock=media_lock),
        # Advances the slideshow; occasionally re-downloads the album cache.
        Probe(
            "refresh-photos-slideshow.py",
            slide,
            _env_float("PEDRO_PHOTOS_PROBE_TIMEOUT", 600),
            lock=media_lock,
            retry=30,
            skip_if=_photos_rotator_alive,
        ),
        # Repaints idle voice state only if the voice daemon died.
        Probe("refresh-voice-console.py", base, 30, python="voice"),
    ]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="run every probe once and exit")
    parser.add_argument(
        "--base-interval",
        type=float,
        default=_env_float("PEDRO_STATE_REFRESH_INTERVAL", 20),
        help="cadence of the fast local probes (seconds, default 20)",
    )
    parser.add_argument("--status-file", type=Path, default=None)
    args = parser.parse_args(argv)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    refresher = Refresher(build_probes(max(1.0, args.base_interval)), args.status_file)
    if args.once:
        return refresher.run_once()

    def _shutdown(signum, _frame):
        refresher.stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    return refresher.run_forever()


if __name__ == "__main__":
    sys.exit(main())
