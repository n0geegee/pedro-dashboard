# Pedro Dashboard v1.4.8 — photos: native fetch + monotonic advance + orientation

Released: 2026-06-19 by Pedro (iMac-Hermes).

## What changed

### `scripts/refresh-photos-slideshow.py` (+77/-~5)

- `pick_image` now advances by **exactly one slot per probe** (uses
  `media.json.slideshow.current` to remember position). Replaces the
  old `(now / interval) % total` calculation which skipped 3-4 items
  per refresh on the 20 s state-refresher cadence.
- Fetches Google Photos at **source resolution** (`=s0` URL suffix)
  instead of capped thumbnail. Portrait orientation (e.g. phone
  vertical photos) was being clipped by the `cover` CSS.
- Reads **EXIF orientation tag** via Pillow (when available) and
  emits `width / height / orientation` in the manifest. Frontend
  JS uses these to honour portrait crops instead of always `cover`.

### `scripts/_lifecycle_common.sh` (photos env block, ~10 lines)

- `PEDRO_GOOGLE_PHOTOS_REFRESH_SECONDS` — default 300 (5 min).
- `PEDRO_GOOGLE_PHOTOS_MAX_IMAGES` — default 300 (was 80; user
  album has 246 items as of 2026-06-16).
- `PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS` — default 5 (was 45 in
  Python script; 5 s × 220 items = ~18 min full cycle).

### `scripts/photos-rotator.sh` (NEW, 159 lines)

- Daemon that calls `refresh-photos-slideshow.py` every
  `PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS` (default 5 s).
- `--start | --stop | --status` subcommands.
- Keeps the photos probe decoupled from the 20 s state-refresher
  cadence (which fans out to many other probes and shouldn't
  be sped up just for slideshow snappiness).

### `.gitignore`

Added `.test/` (scratch recordings used during dev; never to
be committed).

## Caveats (Codex-audit findings)

- **PIL missing from `.venv-voice`** — the script imports Pillow
  defensively: `try: from PIL import Image; _HAVE_PIL = True`.
  If absent, manifest emits `width/height/orientation: null` and
  JS falls back to legacy `cover` behaviour. **Not a blocker** —
  install with `pip install Pillow` inside `.venv-voice` if
  portrait orientation matters.
- **Bandwidth** — `=s0` fetches full-resolution photos (~3-5 MB each).
  At 5 s rotation × 5 MB ≈ 60 MB/min sustained on a kiosk with a
  slideshow widget. Acceptable on home Wi-Fi; may need `=s2048` cap
  on a metered link.

## What did NOT change

- `app/server.py`, frontend HTML/JS, kiosk, voice subsystem — unchanged.
- Photos manifest schema is backward-compatible: existing JS keeps
  working when new fields are null.
- Voice KWS daemon (separate release v1.4.9).

## Rollback

```bash
git checkout v1.4.7 -- scripts/refresh-photos-slideshow.py \
                       scripts/_lifecycle_common.sh \
                       scripts/photos-rotator.sh \
                       .gitignore
```

## Related

- v1.4.7 release note: `docs/releases/PEDRO_DASHBOARD_V1.4.7.md`
- Codex audit: see Pedro session log 2026-06-19 18:45-19:10
- Recovery plan: `~/.hermes/state/pedro-dashboard-recovery-plan.md`