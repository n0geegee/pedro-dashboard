#!/usr/bin/env python3
"""Pedro Dashboard — Google Photos public album slideshow connector.

Uses Jurand's public Google Photos shared album as a continuously refreshable
source. The dashboard renders local cached images instead of hitting Google on
every browser refresh. This is intentionally separate from Google Photos Picker:
Picker is official/manual selection; the public album link is better for a
hands-off display album that Jurand can keep adding photos to.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _probe_common import atomic_write, envelope, now_iso, resolve_state_dir  # noqa: E402

WIDGET = "media"
DEFAULT_ALBUM_URL = "https://photos.google.com/share/AF1QipMdT3_Rs-wS-anKMch21iIC3WXenBIeih3IAvCvZ-LkE4l-YtnkiknUdiOR9vNWqQ?key=MWJ4a2o1QkR0Q2xLZmI3TEJodTZJZFY0emlnNG1R"
DEFAULT_ALBUM_TITLE = "pedro slideshow"
DEFAULT_REFRESH_SECONDS = 1800
DEFAULT_SLIDE_SECONDS = 45
DEFAULT_MAX_IMAGES = 80
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


def extract_photo_urls(html: str, max_images: int) -> list[str]:
    raw = re.findall(r"https://lh3\.googleusercontent\.com/[^\\\"'<> )]+", html)
    urls: list[str] = []
    seen: set[str] = set()
    for u in raw:
        if "/pw/" not in u:
            continue
        # Normalize escaped unicode remnants and request a dashboard-friendly size.
        u = u.replace("\\u003d", "=")
        u = re.sub(r"=(?:w\d+-h\d+|s\d+)(?:-[a-z]+)*$", "=w1400-h900-no", u)
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
        if len(urls) >= max_images:
            break
    return urls


def fetch_album_urls(album_url: str, max_images: int) -> list[str]:
    req = urllib.request.Request(album_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read(2_500_000).decode("utf-8", "ignore")
    return extract_photo_urls(html, max_images=max_images)


def download_if_needed(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 10_000:
        return False
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = resp.read(8_000_000)
    if len(data) < 10_000:
        raise RuntimeError("downloaded_image_too_small")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return True


def cache_album(album_url: str, cache_dir: Path, manifest_path: Path, max_images: int) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    urls = fetch_album_urls(album_url, max_images=max_images)
    if not urls:
        raise RuntimeError("no_photo_urls_found")
    images = []
    downloaded = 0
    for idx, url in enumerate(urls, start=1):
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        dest = cache_dir / f"photo-{idx:03d}-{digest}.jpg"
        try:
            if download_if_needed(url, dest):
                downloaded += 1
        except Exception as exc:
            # Skip individual broken image but keep the album usable.
            images.append({"url": url, "error": type(exc).__name__})
            continue
        images.append({
            "source_url": url,
            "file": str(dest),
            "public_url": "/static/cache/photos/" + dest.name,
        })
    images = [x for x in images if x.get("public_url")]
    if not images:
        raise RuntimeError("no_images_cached")
    manifest = {
        "album_url": album_url,
        "album": DEFAULT_ALBUM_TITLE,
        "updated_at": now_iso(),
        "count": len(images),
        "downloaded": downloaded,
        "images": images,
    }
    atomic_write(manifest_path, manifest)
    return manifest


def load_or_refresh_manifest(album_url: str, cache_dir: Path, manifest_path: Path, refresh_seconds: int, max_images: int) -> dict[str, Any]:
    existing = read_json(manifest_path)
    if existing and existing.get("images"):
        age = time.time() - manifest_path.stat().st_mtime
        if age < refresh_seconds:
            return existing
    return cache_album(album_url, cache_dir, manifest_path, max_images=max_images)


def pick_image(manifest: dict[str, Any], slide_seconds: int) -> tuple[int, dict[str, Any]]:
    images = [x for x in manifest.get("images", []) if isinstance(x, dict) and x.get("public_url")]
    if not images:
        raise RuntimeError("manifest_has_no_images")
    idx = int(time.time() // max(5, slide_seconds)) % len(images)
    return idx + 1, images[idx]


def main() -> int:
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
        manifest = load_or_refresh_manifest(album_url, cache_dir, manifest_path, refresh_seconds, max_images=max_images)
        current, image = pick_image(manifest, slide_seconds=slide_seconds)
        total = int(manifest.get("count") or len(manifest.get("images") or []))
        data["slideshow"] = {
            "album": album_title,
            "total": total,
            "current": current,
            "provider": "google_photos_shared_album_cache",
            "source_url": album_url,
            "image_url": image["public_url"],
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


if __name__ == "__main__":
    raise SystemExit(main())
