# Pedro Dashboard v1.5 — state refresher as one scheduler

## What changed

### NEW: `scripts/pedro_refresher.py`

Replaces the bash loop that ran every probe back to back and then slept
20 s. One long-lived Python process now schedules each probe on its own
cadence. Probes stay separate scripts run as subprocesses, because they
need different interpreters (system / Hermes venv / voice venv).

| Probe | Cadence | Notes |
|---|---|---|
| mock baseline, system, hermes, openviking, polsat, voice heartbeat | 20 s (`--interval`) | local, cheap |
| photos slideshow | `PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS` (5 s) | replaces `photos-rotator.sh` |
| route | 60 s | probe keeps its own 5 min throttle |
| calendar | 120 s | `PEDRO_CALENDAR_INTERVAL` |
| weather, VNL, season skin | 300 s | `PEDRO_WEATHER_INTERVAL`, `PEDRO_VNL_INTERVAL`, `PEDRO_SKIN_INTERVAL` |

- **Hard timeout per run** (30–60 s; photos `PEDRO_PHOTOS_PROBE_TIMEOUT`,
  600 s). A hung probe is killed along with its process group and no longer
  stalls the other widgets.
- **Faster retry on failure**: a failing probe is retried after
  min(cadence, 60 s) instead of waiting for its full cadence.
- **No lost updates on `media.json`**: polsat and photos never run at the
  same time.
- **No mock flicker**: the mock baseline skips `system` / `hermes` /
  `openviking`, which have live probes. When one of those probes fails, its
  card now shows `stale` / `error` instead of mock data with status `ok`.
- **Quiet log**: `state-refresher.log` only records state changes (a probe
  starts failing, with the last stderr lines, or recovers). It no longer
  writes "refresh ok" every 20 s.
- **Status**: `scripts/state-refresher.sh --status` lists every probe with
  its cadence, last successful run and failure count (from
  `$PEDRO_RUN_DIR/state-refresher.status.json`).

### Changed

- `state-refresher.sh`: same `--start/--stop/--status/--loop` interface;
  `--loop` now execs the scheduler. `--stop` also recognises the pre-v1.5
  bash loop.
- `refresh-all-state.sh`: now `pedro_refresher.py --once` (all probes once,
  in parallel). `start-dashboard.sh` still calls it before the server starts.
- `_lifecycle_common.sh`: `pedro_load_probe_env` (DISPLAY fallback +
  `~/.hermes/.env`), shared by both wrappers.
- `write-mock-state.py`: `--skip` option; the atomic writer now comes from
  `_probe_common.py` (as it does in `refresh-season-skin.py`).
- `app.js`: skips a poll while the previous `/api/state` request is still in
  flight and aborts requests that take longer than one poll period.
- Removed `app/static/styles.css.bak-before-spring-fairytale-preview-20260615-230815`
  (unused, and it was publicly served under `/static/`).

## Upgrade on the iMac

```bash
git pull
scripts/state-refresher.sh --stop && scripts/state-refresher.sh --start
scripts/photos-rotator.sh --stop      # if it was running; no longer needed
scripts/state-refresher.sh --status
```

Autostart entries (`install-autostart.sh`) do not change.
