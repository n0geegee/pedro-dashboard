# Slideshow hotfix — 2026-09-18

## Result
Installed persistent shuffled rounds on imac-hermes. Each stable 277-photo inventory is consumed exactly once before the next shuffle. Inventory refresh cannot reset the playback queue. Existing five-second cadence, fullscreen schedule, frontend, privacy, Voice and Polsat configuration are unchanged. No service or kiosk restart was needed.

## Implementation
- scripts/refresh-photos-slideshow.py separates inventory from playback order.
- media.json atomically holds the current slide and internal _photos_cycle (album fingerprint, round, queue, consumed position), under the existing media writer lock.
- The existing server envelope excludes _photos_cycle from the polling API. Polsat preserves it while updating its own fields.
- New photos wait for the next round; deleted photos are skipped. A process restart resumes the saved queue. The first activation starts a new round because the old implementation did not record a reliable seen set.
- No adjacent repeat at a round boundary when more than one photo exists.
- A failed advance leaves the previous committed slide and cursor untouched and reports failure.

## Verification
- Baseline: 78 Python tests PASS. The new pipeline test first failed on early repeats; two additional red-to-green checks covered failed commits and inventory-only refresh.
- Candidate and installed full suites: 87 tests PASS. No new dependencies.
- Ten seeded cases each completed three full 277-photo rounds with inventory reordering during playback; each round covered all entries once.
- Native Linux integration: 277 separate CLI processes, 277 unique selections, five inventory reorders; PASS.
- Actual CLI restart, membership changes, API queue exclusion and preservation through a Polsat update: PASS.
- Additional failure/retry-next-entry and deletion of already-consumed/current entries: PASS.
- Independent read-only code review: PASS, no material security or logic blockers. Reviewed diff SHA-256: 53cd2d1ed366e22dbfe91b249a7fbebcbc1be878675de5577e49742484cb2b84.
- Live acceptance: 56 selections, 56 unique, cursor 9 -> 64, 275.6 seconds. Natural album refresh observed; queue hash unchanged; no repeat, skip or reset. API health OK; no internal queue in API.
- This live observation is a partial real-time round, not a claim that a complete 23-minute round or every physical screen paint was observed. Complete-round verification above used the real selector/pipeline and separate CLI processes in isolated fixtures.
- app.js SHA-256 unchanged: 006f3d0729801cfbf3a8733fccabe8b19a7d6fcbed5ff31096f4b812a958c3a0.

## Deployment and recovery
Source SHA-256: 4f0e9d7eec2701d12ab36ba9c97daded6de7cabe305842d169398b881cf825ce
Tests SHA-256: fbed46a3eb21cb1a8b734b31af25b88a5d76f25d1056becdf25ba83a61f69aaa
Backup: /home/imac-hermes/projects/pedro_dashboard_backups/slideshow-cycle-20260918T160127Z
Original source SHA-256: 3851845cbf2fcc80155925c327887a7bb5bfb6bee4dbca4a2c8fe0e2bc437ce5.
Backup includes the original selector and baseline identity; deployment used an atomic source replacement under existing media/manifest locks. The previous selector ignores the new top-level cycle field if rollback is necessary. Rollback is not an improvement: it restores the diagnosed premature-reshuffle defect.

Controller evidence: C:/Users/PthaloBlue/AppData/Local/Temp/pedro-slideshow-audit/
No push or unrelated pending 1.4.12 rollout was performed. Health version remains 1.4.11; identify this hotfix by the Git commit and source hash.
