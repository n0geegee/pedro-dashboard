# Pedro Dashboard v1.4.2 — backend minimax token counter (standalone endpoint)

Released: 2026-06-19 by Pedro (iMac-Hermes).

## What changed

### `app/server.py` — standalone `/api/minimax_usage` endpoint

Added a backend-only endpoint that exposes MiniMax M3 5-hour rolling-window
token usage data. The data is collected by a separate sniffer daemon
(`~/.local/bin/hermes-minimax-sniff.sh`) that tails the Hermes agent log
(`~/.local/state/hermes/agent.log`), parses `API call #N: ...` lines for
`provider=minimax` entries, and writes a per-session + 5-hour-window
aggregation to `~/.local/state/herhes/minimax-usage.json` via
`~/.local/bin/hermes-minimax-update.py`.

The new route is mounted as a standalone GET:
- `GET /api/minimax_usage` → returns:
  ```json
  {
    "status": "ok",
    "five_h_in": 8400000,
    "five_h_out": 26000,
    "five_h_requests": 72,
    "sessions": 30,
    "all_time_in": 251000000,
    "all_time_out": 1200000,
    "as_of": "2026-06-19T13:55:00+02:00"
  }
  ```

## What did NOT change

- **Kiosk UI is unaffected.** This endpoint is NOT registered in the
  `/api/state` widgets dict. The frontend never calls it. Jurand will
  design and integrate the dashboard widget himself in a future release.
- Oracle skin, volleyball fetcher, slideshow, photos rotator — unchanged.
- v1.4.1 volleyball UX polish (commit 4d6095c) — unchanged.

## Verification

```bash
# Endpoint responds
curl -s http://127.0.0.1:17888/api/minimax_usage | python3 -m json.tool

# Confirm kiosk UI is unaffected
curl -s http://127.0.0.1:17888/api/state | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('widgets:', list(d['widgets'].keys()))"
# Expected: widgets do NOT include 'minimax_usage'

# Sniffer is live
ps -ef | grep hermes-minimax-sniff | grep -v grep | head -1

# Data store exists and is non-trivial
ls -la ~/.local/state/hermes/minimax-usage.json
```

## Rollback

- `git revert v1.4.2` keeps v1.4.1 frontend, removes only this commit.
- Or: `git checkout v1.4.1 -- app/server.py` to restore server.py to v1.4.1.
- The standalone sniffer daemon and data store live outside the repo and
  are unaffected by git rollback.

## Related

- Sniffer script: `~/.local/bin/hermes-minimax-sniff.sh` (daemon, no UI)
- Updater: `~/.local/bin/hermes-minimax-update.py` (Python, atomic rename writes)
- Data store: `~/.local/state/hermes/minimax-usage.json`
- Recovery plan: `~/.hermes/state/pedro-dashboard-recovery-plan.md`
