# Pedro Dashboard Durable Slot Runtime Handoff Plan

> **For Hermes:** Execute this plan only after inspecting the live worktree. Preserve unrelated changes and verify every Git/remote side effect.

**Goal:** Make the already-working replaceable-slot implementation discoverable and durable for a new Hermes session on the same machine and in a fresh checkout, without losing or falsely mixing the pre-existing dashboard worktree.

**Architecture:** Preserve the existing local refactor history as an explicit checkpoint, then record the slot-runtime implementation and a root `AGENTS.md` handoff in a separate commit. Publish a named branch to `origin`; do not rely on session memory, an untracked plan, or a local-only branch.

**Tech Stack:** Git worktrees, static HTML/JavaScript/JSON, Node built-in tests, Python stdlib tests, live Pedro Dashboard API and kiosk.

---

## Current state and boundary

- Canonical source root: `/home/imac-hermes/projects/pedro_dashboard/`.
- Current local branch: `refactor/runtime-state-privacy-ops-20260622`.
- Current branch has no remote branch on `origin`; `origin` currently exposes only `main`.
- The worktree contains earlier dirty dashboard/backend/ops changes that must be preserved:
  - `app/server.py`
  - `app/static/styles.css`
  - `scripts/_lifecycle_common.sh`
  - `scripts/launch-polsat-box-go.sh`
  - `scripts/refresh-photos-slideshow.py`
  - `scripts/refresh-vnl-volleyball.py`
  - `scripts/start-dashboard.sh`
  - `scripts/start-kiosk.sh`
  - `scripts/watchdog-dashboard.sh`
  - the pre-slot portions of `app/static/app.js` and `app/static/index.html`.
- The slot-runtime delta is bounded by the verified pre-slot backup:
  - `/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_pre_slot_runtime_20260906-124042.tgz`
  - checksum sidecar: `/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_pre_slot_runtime_20260906-124042.tgz.sha256`
- The modularity implementation to persist is:
  - `app/static/slot-runtime.js`
  - `app/static/slot-layout.json`
  - `tests/test_slot_runtime.js`
  - the post-backup changes in `app/static/app.js` and `app/static/index.html`
  - `.hermes/plans/2026-09-06_124042-slot-runtime.md`
- Current assignment is explicit: `UL=volleyball`, `UR=polsat-status`, `LL=birdwatch`, `LR=photos`.
- `LL=birdwatch` is an assignment, not a semantic slot identity; a future `volleyball-grid` module can replace it through the config/registry.

## Durable handoff design

Create `AGENTS.md` at the repository root. It must state, in concise factual terms:

- this repository already contains the v1 replaceable slot runtime;
- the canonical durable branch name;
- the exact runtime/config/test/plan files;
- the current four assignments;
- the shell boundary (left column, ticker, clock, skins, grid, fullscreen overlay remain shell-owned);
- that `volleyball-grid` is future work, not currently implemented;
- the verified test and screenshot commands;
- the backup/recovery artifact;
- a start-of-session rule: inspect `git status`, read `AGENTS.md`, and do not reset/clean a dirty tree or treat modularity as an unimplemented TODO.

The handoff must describe evidence and re-verification commands, not blindly assert that the live server or kiosk is healthy.

## Ordered execution

### 1. Freeze and back up the current state

- Create a new dated archive of the current checkout outside the repository, excluding volatile runtime logs/state and `.git`.
- Write and verify a SHA-256 sidecar.
- Record current branch/status and the backup path.
- Do not reset, clean, blindly stash, or overwrite the live checkout.

### 2. Build history in an isolated temporary worktree

- Create a detached temporary worktree from the current branch `HEAD`.
- Rehydrate only the tracked pre-slot files from the verified pre-slot backup.
- Stage the known pre-existing dirty tracked files explicitly, never with `git add .`.
- Commit them as an honest checkpoint, e.g.:
  - `chore(checkpoint): preserve dashboard refactor baseline`
- Copy the current post-slot `app.js`/`index.html`, the three new runtime/config/test files, the original slot plan, and `AGENTS.md` into the temporary worktree.
- Stage only those exact handoff/modularity paths.
- Commit them separately, e.g.:
  - `feat(slots): make dashboard slot runtime durable`
- Run a staged-diff secret check that reports only pass/fail/counts and never prints credential values.

### 3. Publish a named branch

- Use the explicit branch name `refactor/pedro-dashboard-slot-runtime`.
- Push it with `git push -u origin HEAD` or the exact branch ref; never force-push.
- Verify the exact remote ref and SHA with `git ls-remote --heads origin`.
- Verify the local branch has an upstream and the committed tree is clean in the temporary worktree.

### 4. Make the live checkout use the durable branch

- Before switching, verify the current tracked files are byte-identical to the final temporary branch tree.
- Move only known untracked copies temporarily if Git would otherwise report an overwrite risk; do not delete project data.
- Switch `/home/imac-hermes/projects/pedro_dashboard/` to the published durable branch.
- Set its upstream to the exact `origin` branch.
- Verify `git status --short --untracked-files=all` is clean except intentionally ignored runtime state.
- Confirm the old local-only branch is an ancestor of the durable branch, then delete only that redundant local ref. Do not delete the remote durable branch.

### 5. Fresh-session/fresh-checkout acceptance

From `origin/refactor/pedro-dashboard-slot-runtime` in a new temporary worktree:

- assert `AGENTS.md` exists and contains the slot-runtime handoff markers;
- assert Git tracks the runtime, layout, tests, implementation plan, and `AGENTS.md`;
- assert the checkout is clean;
- run:
  - `node --check app/static/slot-runtime.js`
  - `node --check app/static/app.js`
  - `node tests/test_slot_runtime.js`
  - `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- verify the result is from the remote branch, not merely the original dirty worktree.

### 6. Live acceptance

- Verify `/api/health` on `127.0.0.1:17888` and required `/api/state` widget keys.
- Restart only the kiosk if the final branch switch changed served static content; otherwise still verify the running Chrome process and capture a fresh X11 screenshot.
- Capture a real screenshot at `1920x1200`.
- Inspect that the ordinary dashboard remains visible without the fullscreen slideshow overlay, all four slots retain their geometry, LL remains Birdwatch, and ticker/clock/left shell are intact.

## Acceptance criteria

- A fresh checkout from the remote durable branch contains the code and the handoff without relying on session history.
- The durable branch exists on `origin` and has a verified SHA.
- The live repository is on that upstream branch with a clean tracked worktree.
- The earlier local-only branch is removed only after its commits are reachable from the durable branch.
- The pre-existing dirty work is preserved in a named checkpoint rather than silently mixed into the feature commit.
- Runtime tests, the full Python test suite, API checks, and fresh screenshot verification pass.
- No credentials or raw secrets are printed or added to handoff documentation.

## Recovery

- Primary file-level recovery: `/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_pre_slot_runtime_20260906-124042.tgz` and its `.sha256` file.
- New pre-handoff archive: `/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_pre_durable_handoff_20260906-133110.tgz` with SHA-256 sidecar at the same path plus `.sha256`.
- If a Git step fails, leave the live worktree untouched, retain the temporary worktree and backup, and report the exact failing command.
- Never use `git reset --hard`, `git clean`, or a guessed rollback path as cleanup.
