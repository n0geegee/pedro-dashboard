# Pedro Dashboard Slot Runtime — canonical architecture handoff

**Status:** implemented and verified v1, 2026-09-06  
**Repository:** `/home/imac-hermes/projects/pedro_dashboard`  
**Durable branch:** `refactor/pedro-dashboard-slot-runtime`  
**Remote:** `origin/refactor/pedro-dashboard-slot-runtime`  
**Stack:** Python backend + static HTML/CSS + vanilla JavaScript; no React, bundler, Shadow DOM, or arbitrary dynamic imports.

This document is the canonical repository handoff for future Hermes sessions. Read it together with the root `AGENTS.md`; do not rely on a Discord message, a session summary, an untracked file, Git notes, or local model memory as the source of truth.

## Executive status

The dashboard has a **slot runtime v1** over the existing visual shell. The four replaceable card surfaces are addressed by stable slot IDs:

- `UL` → `volleyball`
- `UR` → `polsat-status`
- `LL` → `birdwatch`
- `LR` → `photos`

`LL` is a replaceable slot, not a permanent Birdwatch identity. Birdwatch is the current assignment. A future `volleyball-grid` module must first be added to the allowlisted registry and tested; only then should the `LL` assignment change to:

```json
"LL": { "module": "volleyball-grid", "enabled": true }
```

The following remain shell-owned and are **not** replaceable slot modules in v1:

- the 2×2 grid and card geometry;
- the left utility column;
- ticker and clock;
- skin layers;
- fullscreen Google Photos overlay/controller;
- global page lifecycle and kiosk behavior.

The implementation is intentionally a thin adapter seam over existing renderers. It is not a claim that every renderer has already been extracted into an independent source file.

## Durable Git history

The branch was published without a force-push and is now the canonical handoff branch on `origin`:

1. `0c94412` — existing committed Birdwatch probe foundation.
2. `068cd3d` — `chore(checkpoint): preserve dashboard refactor baseline`. This explicitly records the pre-slot dirty worktree that existed before the runtime work. It contains earlier dashboard changes as a checkpoint; it must not be described as a slot-only commit.
3. `130bfea` — `feat(slots): make dashboard runtime durable`. This contains the runtime/config/test integration and the first durable handoff files.
4. `01d7829` — `docs(handoff): record durable slot branch and recovery`. This records the exact current-state backup and recovery artifact.
5. The commit containing this architecture document and the status/decision links is discoverable with:

   ```bash
   git log --oneline -- docs/architecture/SLOT_RUNTIME.md
   ```

The old local-only branch `refactor/runtime-state-privacy-ops-20260622` was an ancestor of this branch and was deleted only after an ancestor check. Do not recreate it merely because an old session summary mentions it.

The checkpoint boundary is deliberate: the live `app.js`/`index.html` contained mixed pre-existing work, so forcing a fake feature-only commit would have risked dropping dependencies. If a future maintainer wants a cleaner stacked PR, do that as a separate reviewed history rewrite; do not reset this working branch blindly.

## Runtime contract

### Configuration

`app/static/slot-layout.json` is the versioned assignment document:

```json
{
  "schema_version": 1,
  "engine": "slots-v1",
  "revision": "baseline-birdwatch-1",
  "slots": {
    "UL": { "module": "volleyball", "enabled": true },
    "UR": { "module": "polsat-status", "enabled": true },
    "LL": { "module": "birdwatch", "enabled": true },
    "LR": { "module": "photos", "enabled": true }
  }
}
```

The config is not executable code and cannot load arbitrary paths. The runtime validates the schema, slot IDs, enabled/disabled values, module IDs, supported-slot constraints, and duplicate/invalid assignments before mounting.

### Registry and lifecycle

`app/static/slot-runtime.js` owns an explicit allowlist and a narrow lifecycle:

- `select(input, ctx)` derives the module input without DOM writes;
- `mount(ctx)` creates module-owned content inside the existing host;
- `update(ctx, input, instance)` updates an unchanged assignment;
- `unmount(ctx, instance)` releases private resources;
- per-slot `AbortController` cancels the old generation;
- a generation guard rejects late asynchronous completions;
- one module failure becomes a bounded local fallback and does not stop sibling slots;
- disabled or invalid assignments use an explicit fallback.

`app/static/index.html` keeps the existing IDs/classes and adds `data-slot="UL|UR|LL|LR"`. It loads the runtime before `app.js`. `app/static/app.js` supplies the adapters for `volleyball`, `polsat-status`, `birdwatch`, and `photos`, while leaving shell-owned behavior outside the runtime.

### Ownership rules

A module may own only the inside of its assigned existing `<article class="card">` host. It must not rewrite:

- another slot;
- grid/layout CSS;
- ticker or clock;
- left-column utilities;
- skin state;
- the fullscreen overlay controller.

Do not introduce React, Shadow DOM, a bundler, arbitrary dynamic imports, or a second central switch merely to change an assignment.

## Verification evidence

The implementation was tested both from the isolated durable checkout and against the live dashboard:

```text
node --check app/static/slot-runtime.js       OK
node --check app/static/app.js                OK
node tests/test_slot_runtime.js               4 passed
python3 -m unittest discover -s tests -p 'test_*.py' -v   42 tests, OK
```

A fresh detached checkout from `origin/refactor/pedro-dashboard-slot-runtime` also had a clean `git status`, found all handoff/runtime files tracked, and repeated the Node and Python suites successfully.

Live checks:

- backend: `http://127.0.0.1:17888/api/health` returned healthy;
- served `slot-runtime.js` and `slot-layout.json` matched the repository files;
- kiosk: Chrome dashboard window present at `1920x1200`;
- final screenshot after waiting for compositor paint: `/tmp/pedro-shots/slot-runtime-durable-final-after-paint.png`;
- screenshot geometry: `1920x1200`;
- screenshot SHA-256: `6d4a88f200d9a8a492a823d15193375c2b729b367c40d7b1cb5b58fec9f58b77`;
- visual result: ordinary dashboard visible, four slot regions present, `LL` Birdwatch, no fullscreen Google Photos overlay, no scroll or grid collapse. The Polsat player/status surface is allowed to occupy `UR`.

The first screenshot attempt was taken immediately after the kiosk bounce and captured the desktop before Chrome painted. That was a failed timing check, not accepted evidence; the screenshot above was taken after the dashboard window was confirmed and paint had settled.

## Recovery artifact

A pre-handoff backup exists outside GitHub:

```text
/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_pre_durable_handoff_20260906-133110.tgz
```

SHA-256:

```text
46878622e317c8b4ec3852eae30c416bb3656993f28816fddbac10c961f2f635
```

Do not commit the archive, runtime state, logs, credentials, or private tokens. If recovery is needed, inspect the backup and Git history first. Do not use `git reset --hard`, `git checkout -- .`, `git clean`, or a blind stash to make a dirty tree look clean.

## Start-of-session procedure

1. Read this file and `AGENTS.md`.
2. Run:

   ```bash
   git status --short --branch
   git log --oneline --decorate -6
   git branch -vv
   ```

3. Confirm the current branch is `refactor/pedro-dashboard-slot-runtime` or a reviewed descendant, and that the remote ref exists.
4. Treat the four assignments above as current until a deliberate config change is made.
5. Before frontend edits, make a fresh backup and verify the live root; preserve unrelated work.
6. After any static asset change, restart the kiosk with `DISPLAY=:0`, wait for paint, and inspect a real `1920x1200` screenshot. Syntax or HTTP 200 alone is not visual proof.
7. If changing `LL`, add and test the new allowlisted module before editing `slot-layout.json`.

## Known v1 limits

- The runtime is an adapter layer; full renderer extraction is future work.
- The legacy renderer internals and some media dependencies remain in `app.js` by design.
- The fullscreen slideshow remains shell-owned and default-disabled for the ordinary kiosk.
- Existing unrelated widget freshness/state caveats are not slot-runtime failures; inspect `/api/state` and the widget-specific contracts separately.
- The root `README.md` and older decision text contain historical plan/Voice Console language. The dated section added for this handoff and this document define the current slot-runtime status; do not erase the historical product contract without a separate decision.

## Future replacement example

When `volleyball-grid` is implemented and tested, the intended LL-only change is:

```diff
-"LL": { "module": "birdwatch", "enabled": true }
+"LL": { "module": "volleyball-grid", "enabled": true }
```

No layout rewrite, shell migration, fullscreen-controller rewrite, or arbitrary module loading is required for that assignment change.
