#!/usr/bin/env python3
"""Pedro Dashboard — Google Photos public album slideshow connector.

Uses Jurand's public Google Photos shared album as a continuously refreshable
source. The dashboard renders local cached images instead of hitting Google on
every browser refresh. This is intentionally separate from Google Photos Picker:
Picker is official/manual selection; the public album link is better for a
hands-off display album that Jurand can keep adding photos to.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import (
    atomic_write,
    envelope,
    manifest_state_lock,
    media_state_lock,
    now_iso,
    resolve_state_dir,
)  # noqa: E402

try:
    from PIL import Image as _PILImage
    _HAVE_PIL = True
except Exception:
    _PILImage = None
    _HAVE_PIL = False

WIDGET = "media"
DEFAULT_ALBUM_URL = "https://photos.google.com/share/AF1QipMdT3_Rs-wS-anKMch21iIC3WXenBIeih3IAvCvZ-LkE4l-YtnkiknUdiOR9vNWqQ?key=MWJ4a2o1QkR0Q2xLZmI3TEJodTZJZFY0emlnNG1R"
DEFAULT_ALBUM_TITLE = "pedro slideshow"
DEFAULT_REFRESH_SECONDS = 1800
DEFAULT_SLIDE_SECONDS = 3
# A positive value is an optional operator cap. Zero means "all photo URLs
# discoverable in the album page"; the production default must not silently
# drop the 301st photo just because an old album happened to have 300 items.
DEFAULT_MAX_IMAGES = 0
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) PedroDashboard/0.1"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def state_path(state_dir: Path) -> Path:
    return state_dir / "media.json"


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_media_baseline(path: Path) -> dict[str, Any]:
    existing = read_json(path)
    if existing and isinstance(existing.get("data"), dict):
        return existing
    return envelope(WIDGET, "ok", 120, {"transmission": {}, "slideshow": {}, "tbd": {}})


def extract_photo_urls(html: str, max_images: int | None = None) -> list[str]:
    raw = re.findall(r"https://lh3\.googleusercontent\.com/[^\\\"'<> )]+", html)
    urls: list[str] = []
    seen: set[str] = set()
    for u in raw:
        if "/pw/" not in u:
            continue
        # Normalize escaped unicode remnants and request a dashboard-friendly size.
        u = u.replace("\\u003d", "=")
        # Use =s0 (original / no resize) — GPhotos returns the source asset at
        # its native resolution. Some album HTML URLs already end with =w... or
        # =s..., but many have no size suffix at all. A naked lh3 URL defaults
        # to a tiny ~512px preview, which looks awful when the dashboard promotes
        # it to fullscreen. Normalize both cases to =s0 before hashing/caching.
        sized = re.sub(r"=(?:w\d+-h\d+|s\d+)(?:-[a-z]+)*$", "=s0", u)
        if sized == u and not u.endswith("=s0"):
            u = u + "=s0"
        else:
            u = sized
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
        if max_images is not None and max_images > 0 and len(urls) >= max_images:
            break
    return urls


def fetch_album_urls(album_url: str, max_images: int | None = None) -> list[str]:
    req = urllib.request.Request(album_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        # Read the complete page. The old 2.5 MB read limit could silently
        # truncate a growing album's HTML and turn a partial feed into a
        # smaller-but-valid manifest. If the server advertises a length,
        # verify that the complete response arrived before parsing it.
        declared_length = resp.headers.get("Content-Length")
        body = resp.read()
    if declared_length:
        try:
            if len(body) != int(declared_length):
                raise RuntimeError("album_html_truncated")
        except ValueError:
            pass
    html = body.decode("utf-8", "ignore")
    return extract_photo_urls(html, max_images=max_images)


# Output target for the cached photo. We deliver WebP at kiosk-friendly
# dimensions so Chrome decodes 4-6× smaller payloads than the native =s0 JPEG
# returned by GPhotos (panoramas of 4032×3024 land at ~700 KB WebP instead of
# ~6 MB JPEG), and renders the next slide without a visible black gap. The
# resize is a pure shrink (no enlargement) so tiny originals keep their
# detail and never blow up.
WEBP_MAX_W = 1920
WEBP_MAX_H = 1200
WEBP_QUALITY = 82
WEBP_METHOD = 6  # slowest but ~6-10% smaller than method 4; one-shot at cache.


def _is_normalized_webp(path: Path) -> bool:
    """Return whether ``path`` is a kiosk-sized WebP derivative.

    Older cache runs could leave a valid JPEG under the ``.webp`` filename
    when WebP encoding failed. It rendered, but its native multi-megapixel
    decode could take longer than the three-second rotation deadline.
    """
    if not path.exists():
        return False
    try:
        with path.open("rb") as handle:
            header = handle.read(12)
        if header[:4] != b"RIFF" or header[8:12] != b"WEBP":
            return False
        if not _HAVE_PIL:
            return True
        with _PILImage.open(path) as img:
            width, height = img.size
        return width <= WEBP_MAX_W and height <= WEBP_MAX_H
    except Exception:
        return False


def _normalize_existing_cache(dest: Path) -> None:
    """Transcode a legacy raw cache file in place, preserving it on failure."""
    if _is_normalized_webp(dest):
        return
    if not _HAVE_PIL:
        raise RuntimeError("cached_image_not_normalized_without_pil")

    legacy = dest.with_name(f"{dest.name}.legacy-{os.getpid()}")
    dest.replace(legacy)
    try:
        encode_webp(legacy, dest)
        if not _is_normalized_webp(dest):
            raise RuntimeError("cache_normalization_failed")
    except Exception:
        # ``encode_webp`` may leave a raw fallback at dest. Remove it before
        # restoring the original so a failed repair never destroys the cache.
        try:
            dest.unlink()
        except FileNotFoundError:
            pass
        if legacy.exists():
            legacy.replace(dest)
        raise
    finally:
        try:
            legacy.unlink()
        except FileNotFoundError:
            pass


def download_if_needed(url: str, dest: Path) -> bool:
    """Download or repair the cached WebP derivative for ``url``.

    The cached derivative written to ``dest`` is a WebP resized to
    ``WEBP_MAX_W`` × ``WEBP_MAX_H`` — see :func:`encode_webp`. ``dest``
    therefore ends in ``.webp``, not ``.jpg``; this function only fetches
    the upstream bytes to a side-car temp file when no usable derivative
    exists. Legacy JPEGs already present under the ``.webp`` name are
    transcoded locally so they cannot stall the three-second kiosk cadence.
    """
    if dest.exists() and dest.stat().st_size > 10_000:
        if _is_normalized_webp(dest):
            return False
        _normalize_existing_cache(dest)
        return True
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    raw_tmp = dest.with_suffix(dest.suffix + ".src")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read(8_000_000)
    except Exception:
        # Clean up partial download.
        if raw_tmp.exists():
            try:
                raw_tmp.unlink()
            except Exception:
                pass
        raise
    if len(data) < 10_000:
        try:
            raw_tmp.unlink()
        except Exception:
            pass
        raise RuntimeError("downloaded_image_too_small")
    raw_tmp.write_bytes(data)
    encode_webp(raw_tmp, dest)
    try:
        raw_tmp.unlink()
    except Exception:
        pass
    return True


def encode_webp(src: Path, dest: Path) -> None:
    """Resize ``src`` to ``WEBP_MAX_W`` × ``WEBP_MAX_H`` (no enlargement) and
    write WebP q=82 m=6 to ``dest``.

    Failures fall back to the source bytes (still mostly-cached JPEG,
    decoded by Chrome, but no resize / no WebP savings) so a probe bug
    never bricks the kiosk.
    """
    if not _HAVE_PIL:
        # PIL missing — write the source bytes verbatim so the kiosk still
        # has something to render. Chrome handles JPEG fine; we just lose
        # the resize + WebP savings on this host.
        dest.write_bytes(src.read_bytes())
        return
    try:
        with _PILImage.open(src) as img:
            # Honour EXIF orientation so the resized output matches what the
            # user actually sees when they open the source in a viewer.
            try:
                from PIL import ImageOps as _ImageOps  # type: ignore
                img = _ImageOps.exif_transpose(img)
            except Exception:
                pass
            img.load()
            # Convert to RGB so we can save as WebP (RGBA / palette would also
            # work but RGB keeps the encoder deterministic across sources).
            if img.mode != "RGB":
                img = img.convert("RGB")
            w, h = img.size
            # Compute shrink target — pure shrink, never enlarge.
            scale = min(WEBP_MAX_W / w, WEBP_MAX_H / h, 1.0)
            if scale < 1.0:
                new_w = max(1, int(round(w * scale)))
                new_h = max(1, int(round(h * scale)))
                img = img.resize((new_w, new_h), _PILImage.LANCZOS)
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            img.save(tmp, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD, exact=False)
            tmp.replace(dest)
    except Exception as exc:
        # Last-ditch fallback: copy the source JPEG so Chrome still gets a
        # valid image. Log to the probe's err log via caller.
        try:
            dest.write_bytes(src.read_bytes())
        except Exception:
            pass
        raise


def _measure_image(path: Path) -> dict[str, Any]:
    """Read width/height of a cached image and classify orientation.

    Returns {"width": int|None, "height": int|None, "orientation": str|None}.
    orientation: "portrait" if w/h < 0.95, "landscape" if w/h > 1.05, else "square".
    Returns all None on failure (PIL missing, file unreadable, corrupt) so the
    manifest still loads — JS falls back to the legacy cover behaviour.
    """
    if not _HAVE_PIL or not path.exists():
        return {"width": None, "height": None, "orientation": None}
    try:
        with _PILImage.open(path) as img:
            w, h = img.size
    except Exception:
        return {"width": None, "height": None, "orientation": None}
    if w <= 0 or h <= 0:
        return {"width": None, "height": None, "orientation": None}
    ratio = w / h
    if ratio < 0.95:
        orientation = "portrait"
    elif ratio > 1.05:
        orientation = "landscape"
    else:
        orientation = "square"
    return {"width": w, "height": h, "orientation": orientation}


def shuffle_manifest_order(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Randomize one complete queue without affecting the hot rotator."""
    random.SystemRandom().shuffle(images)
    return images


def cache_album(album_url: str, cache_dir: Path, manifest_path: Path, max_images: int) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    urls = fetch_album_urls(album_url, max_images=max_images)
    if not urls:
        raise RuntimeError("no_photo_urls_found")
    images = []
    downloaded = 0
    for idx, url in enumerate(urls, start=1):
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        # Filename is sha1-only — `idx` (album position) is intentionally NOT
        # in the name because album order is not stable across rebuilds and
        # baking it in produced 4× duplicate files over time (the same source
        # URL would land under photo-167 today, photo-167 after a shuffle
        # tomorrow, photo-171 the next refresh, etc.). The kiosk reads URLs
        # straight from the manifest, so as long as the file is at
        # photo-<sha>.webp and the manifest names it, we are good.
        dest = cache_dir / f"photo-{digest}.webp"
        try:
            if download_if_needed(url, dest):
                downloaded += 1
        except Exception as exc:
            # Skip individual broken image but keep the album usable.
            images.append({"url": url, "error": type(exc).__name__})
            continue
        meta = _measure_image(dest)
        images.append({
            "source_url": url,
            "file": str(dest),
            "public_url": "/static/cache/photos/" + dest.name,
            "width": meta["width"],
            "height": meta["height"],
            "orientation": meta["orientation"],
        })
    images = [x for x in images if x.get("public_url")]
    if not images:
        raise RuntimeError("no_images_cached")

    # Randomize every full manifest refresh, but never on the hot rotation
    # path (`--no-manifest-refresh`). The previous public URL is passed to
    # `pick_image`, so a queue rebuild continues after the visible photo
    # instead of trusting a stale numeric cursor.
    images = shuffle_manifest_order(images)

    manifest = {
        "album_url": album_url,
        "album": DEFAULT_ALBUM_TITLE,
        "updated_at": now_iso(),
        "count": len(images),
        "downloaded": downloaded,
        "order": "random_shuffle_no_repeats_until_wrap",
        "images": images,
    }
    atomic_write(manifest_path, manifest)
    return manifest


def load_or_refresh_manifest(
    album_url: str,
    cache_dir: Path,
    manifest_path: Path,
    refresh_seconds: int,
    max_images: int,
    *,
    allow_refresh: bool = True,
) -> dict[str, Any]:
    existing = read_json(manifest_path)
    if existing and existing.get("images"):
        if not allow_refresh:
            return existing
        age = time.time() - manifest_path.stat().st_mtime
        if age < refresh_seconds:
            return existing
    if not allow_refresh:
        raise RuntimeError("manifest_missing_for_hot_rotation")
    return cache_album(album_url, cache_dir, manifest_path, max_images=max_images)


def pick_image(
    manifest: dict[str, Any],
    slide_seconds: int,
    last_index: int | None = None,
    last_public_url: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Pick the next image for the slideshow.

    Two modes:
      * `last_index is None` (first run / no baseline in media.json) — fall
        back to a deterministic time-based index so the kiosk is not blank.
      * `last_public_url` is present (including after a manifest shuffle) —
        find the current image in the new queue and return the following slot.
      * otherwise, when `last_index` is provided, return
        `(last_index + 1) % len(images)`. This is the "always next, no skips"
        behaviour: every call advances by exactly one position, so the
        dashboard server can be called at any cadence (5s, 20s, 60s) and the
        user will always see a strictly monotonic progression through the
        album. Wall-clock modulo is reserved only as a cold-start fallback
        because it picks a different image on every probe run, which makes
        the rotation look like it is skipping images.
    """
    images = [x for x in manifest.get("images", []) if isinstance(x, dict) and x.get("public_url")]
    if not images:
        raise RuntimeError("manifest_has_no_images")
    if last_public_url:
        for current_idx, item in enumerate(images):
            if item.get("public_url") == last_public_url:
                idx = (current_idx + 1) % len(images)
                return idx + 1, images[idx]
    if last_index is None or last_index < 0 or last_index >= len(images):
        # Cold start / out-of-range fallback. Deterministic on the bucket so
        # two probes within the same slide_seconds window agree.
        idx = int(time.time() // max(5, slide_seconds)) % len(images)
    else:
        idx = (last_index + 1) % len(images)
    return idx + 1, images[idx]


def _refresh_manifest_only() -> int:
    """Refresh only the album manifest; never touch media.json."""
    state_dir = resolve_state_dir(None)
    root = project_root()
    album_url = os.environ.get("PEDRO_GOOGLE_PHOTOS_ALBUM_URL", DEFAULT_ALBUM_URL).strip()
    refresh_seconds = int(os.environ.get("PEDRO_GOOGLE_PHOTOS_REFRESH_SECONDS", DEFAULT_REFRESH_SECONDS))
    max_images = int(os.environ.get("PEDRO_GOOGLE_PHOTOS_MAX_IMAGES", DEFAULT_MAX_IMAGES))
    cache_dir = root / "app" / "static" / "cache" / "photos"
    manifest_path = root / "app" / "state" / "photos_manifest.json"
    try:
        with manifest_state_lock(state_dir):
            existing = read_json(manifest_path)
            if existing and existing.get("images"):
                age = time.time() - manifest_path.stat().st_mtime
                if age < refresh_seconds:
                    print(f"photos manifest fresh (age={int(age)}s)")
                    return 0
            manifest = cache_album(album_url, cache_dir, manifest_path, max_images=max_images)
        print(f"photos manifest refreshed (count={manifest.get('count', 0)})")
    except Exception as exc:
        log_dir = root / "app" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "refresh-photos-slideshow.err.log").open("a", encoding="utf-8") as handle:
            handle.write(f"[{now_iso()}] PHOTOS_MANIFEST_REFRESH_FAILED: {type(exc).__name__}: {exc}\n")
        print(f"photos manifest refresh skipped ({type(exc).__name__})")
    return 0


def _main_locked(*, allow_manifest_refresh: bool = True) -> int:
    state_dir = resolve_state_dir(None)
    root = project_root()
    out_path = state_path(state_dir)
    album_url = os.environ.get("PEDRO_GOOGLE_PHOTOS_ALBUM_URL", DEFAULT_ALBUM_URL).strip()
    album_title = os.environ.get("PEDRO_GOOGLE_PHOTOS_ALBUM_TITLE", DEFAULT_ALBUM_TITLE).strip() or DEFAULT_ALBUM_TITLE
    refresh_seconds = int(os.environ.get("PEDRO_GOOGLE_PHOTOS_REFRESH_SECONDS", DEFAULT_REFRESH_SECONDS))
    slide_seconds = int(os.environ.get("PEDRO_GOOGLE_PHOTOS_SLIDE_SECONDS", DEFAULT_SLIDE_SECONDS))
    max_images = int(os.environ.get("PEDRO_GOOGLE_PHOTOS_MAX_IMAGES", DEFAULT_MAX_IMAGES))
    cache_dir = root / "app" / "static" / "cache" / "photos"
    manifest_path = root / "app" / "state" / "photos_manifest.json"

    media = load_media_baseline(out_path)
    data = media.setdefault("data", {})
    try:
        if allow_manifest_refresh:
            with manifest_state_lock(state_dir):
                manifest = load_or_refresh_manifest(
                    album_url,
                    cache_dir,
                    manifest_path,
                    refresh_seconds,
                    max_images=max_images,
                )
        else:
            manifest = load_or_refresh_manifest(
                album_url,
                cache_dir,
                manifest_path,
                refresh_seconds,
                max_images=max_images,
                allow_refresh=False,
            )
        # Read previous current from media.json so pick_image can advance by
        # exactly one slot instead of jumping to a wall-clock-derived index.
        # `current` is 1-based in the JSON; convert to 0-based for the math.
        prev_current = ((data.get("slideshow") or {}).get("current") or 0)
        prev_image_url = ((data.get("slideshow") or {}).get("image_url") or None)
        last_index = (prev_current - 1) if prev_current > 0 else None
        current, image = pick_image(
            manifest,
            slide_seconds=slide_seconds,
            last_index=last_index,
            last_public_url=prev_image_url,
        )
        total = int(manifest.get("count") or len(manifest.get("images") or []))
        data["slideshow"] = {
            "album": album_title,
            "total": total,
            "current": current,
            "provider": "google_photos_shared_album_cache",
            "source_url": album_url,
            "image_url": image["public_url"],
            "image_orientation": image.get("orientation"),
            "image_width": image.get("width"),
            "image_height": image.get("height"),
            "cache_updated_at": manifest.get("updated_at"),
            "slide_seconds": slide_seconds,
        }
        media["status"] = "ok"
        media["updated_at"] = now_iso()
        media["ttl_seconds"] = 120
        media["error"] = None
        atomic_write(out_path, media)
        print(f"wrote {out_path} (photos ok, current={current}, total={total}, image={image['public_url']})")
        return 0
    except Exception as exc:
        data["slideshow"] = {
            "album": album_title,
            "total": 0,
            "current": 0,
            "provider": "google_photos_shared_album_cache",
            "source_url": album_url,
            "note": "Nie udało się odświeżyć albumu Google Photos",
        }
        media["status"] = "ok"
        media["updated_at"] = now_iso()
        media["error"] = None
        atomic_write(out_path, media)
        log_dir = root / "app" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "refresh-photos-slideshow.err.log").open("a", encoding="utf-8") as f:
            f.write(f"[{now_iso()}] PHOTOS_SLIDESHOW_FAILED: {type(exc).__name__}: {exc}\n")
        print(f"wrote {out_path} (photos unavailable); see app/logs/refresh-photos-slideshow.err.log")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="refresh photos_manifest.json without modifying media.json",
    )
    parser.add_argument(
        "--no-manifest-refresh",
        action="store_true",
        help="rotate from the cached manifest without network refreshes",
    )
    args = parser.parse_args()
    if args.manifest_only and args.no_manifest_refresh:
        parser.error("--manifest-only and --no-manifest-refresh are mutually exclusive")
    if args.manifest_only:
        return _refresh_manifest_only()
    state_dir = resolve_state_dir(None)
    with media_state_lock(state_dir):
        return _main_locked(allow_manifest_refresh=not args.no_manifest_refresh)


if __name__ == "__main__":
    raise SystemExit(main())
