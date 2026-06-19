# Pedro Dashboard v1.4.10 — random slideshow queue

Date: 2026-06-19
Commit: 0a12fad

## What changed

Google Photos slideshow order is now randomized at the manifest/queue level.

`scripts/refresh-photos-slideshow.py` shuffles the cached image list once whenever `photos_manifest.json` is refreshed/rebuilt. The dashboard still advances one slot at a time, so there are no repeats until the shuffled queue wraps.

## What did not change

- No UI/static layout files changed.
- No slideshow card CSS/HTML changed.
- The browser still reads the same `media.json` / `/api/state` slideshow fields.

## Verification

- `python3 -m py_compile scripts/refresh-photos-slideshow.py` passed.
- Existing manifest was shuffled immediately: first entries changed from sequential `photo-001`, `photo-002`, ... to mixed filenames.
- `/api/state` media widget returned status `ok`, current/total fields and image URL.
- Connector advance test passed: after one run, image URL equals the next item in the shuffled manifest.
- Screenshot `/tmp/pedro-slideshow-random-check.png` confirmed the slideshow card is visible and the kiosk layout is not broken.

## Rollback

Use git:

```bash
cd /home/imac-hermes/projects/pedro_dashboard
git revert 0a12fad
```

Runtime state backup before the change:

```text
/home/imac-hermes/.hermes/backups/pedro-slideshow-random-20260619-200409
```
