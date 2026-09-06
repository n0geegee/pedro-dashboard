# Pedro Dashboard — durable session handoff

This repository is the live Pedro Dashboard source tree. **The replaceable slot runtime is already implemented in v1; it is not a TODO or a request to redesign the dashboard.** Read this file before changing the frontend.

## Start here in a new session

1. Confirm the working directory is `/home/imac-hermes/projects/pedro_dashboard/`.
2. Run `git status --short --branch` and `git log --oneline --decorate -8` before editing.
3. Read the slot plan at `.hermes/plans/2026-09-06_124042-slot-runtime.md` and the durable handoff plan at `.hermes/plans/2026-09-06_132832-durable-slot-handoff.md`.
4. Treat the root README as an older product-planning document; this handoff plus the Git history describe the current implementation state.
5. Do not use `git reset --hard`, `git clean`, blind stash, or broad checkout to make a dirty tree look tidy. If the worktree is dirty, identify which changes are pre-existing before editing.

The durable branch for this work is intended to be:

```text
refactor/pedro-dashboard-slot-runtime
```

It must exist on `origin` before this handoff is considered complete. A fresh checkout of that branch must contain this file and all listed runtime files.

## Current slot architecture

The four center/right cards are replaceable through an explicit assignment and an allowlisted local registry:

```text
UL → volleyball
UR → polsat-status
LL → birdwatch
LR → photos
```

`LL` is a slot, not a Birdwatch product identity. `birdwatch` is only the current assignment. A future `volleyball-grid` module can be added to the registry and assigned to `LL` through `app/static/slot-layout.json` without changing the shell or central renderer.

### Runtime files

- `app/static/slot-runtime.js` — `PedroSlotRuntime`, validation, allowlisted registry boundary, lifecycle, cancellation and stale-generation protection.
- `app/static/slot-layout.json` — versioned assignment configuration (`schema_version: 1`, `engine: slots-v1`).
- `app/static/app.js` — runtime integration and legacy-compatible adapters around the existing renderers.
- `app/static/index.html` — stable card IDs plus `data-slot="UL|UR|LL|LR"` metadata and runtime script loading.
- `tests/test_slot_runtime.js` — deterministic Node contract/lifecycle/isolation tests.
- `.hermes/plans/2026-09-06_124042-slot-runtime.md` — original implementation plan.
- `.hermes/plans/2026-09-06_132832-durable-slot-handoff.md` — plan for making this implementation durable and discoverable.

The shell remains responsible for the left utility column, ticker, clock, skin layers, grid geometry and fullscreen slideshow overlay/controller. Do not move those into a slot module unless the user explicitly opens that scope.

## Verification commands

Run from the project root:

```bash
node --check app/static/slot-runtime.js
node --check app/static/app.js
node tests/test_slot_runtime.js
python3 -m unittest discover -s tests -p 'test_*.py' -v
curl -fsS http://127.0.0.1:17888/api/health
curl -fsS http://127.0.0.1:17888/api/state
```

Frontend changes require a real kiosk check at 1920×1200. Keep the normal dashboard visible unless the user explicitly requests fullscreen slideshow behavior.

Last verified baseline before durable handoff:

- Node slot-runtime contract tests: 4 passed.
- Python test suite: 42 tests passed.
- Backend health: loopback `127.0.0.1:17888`.
- Live screenshot: `/tmp/pedro-shots/slot-runtime-final.png` at `1920x1200`.
- The API may report aggregate `stale` for unrelated `hermes`/`openviking` data; do not confuse that with a slot-runtime failure.

## Recovery

A pre-slot implementation backup is available at:

```text
/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_pre_slot_runtime_20260906-124042.tgz
```

The exact pre-handoff current-state backup is:

```text
/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_pre_durable_handoff_20260906-133110.tgz
```

Its SHA-256 sidecar is:

```text
/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_pre_durable_handoff_20260906-133110.tgz.sha256
```

Preserve backups; do not delete project data merely to clean Git state.

## Git boundary

The durable history is intentionally split:

1. a named checkpoint for the already-existing dashboard/backend/ops worktree;
2. a separate slot-runtime + handoff commit.

Do not claim that unrelated earlier changes belong to the slot-runtime feature. Do not amend or rewrite published history without explicit authorization. Prefer small, explicit, verified commits and a remote branch over local-only session state.
