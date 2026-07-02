# skills/assets/series_images.py
"""Manifest-backed image resolution for people/award/office series posters.

This module avoids the brittle pattern of joining sorted image files to sorted
people records. Images are resolved by the record.image_key field instead.

It also supports refresh policies, which matter while migrating away from dirty
legacy caches that used ordinal filenames like 003_John_Adams.png.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont
import requests

from agentic_multimodal.schemas.artifacts import ImageAsset
from agentic_multimodal.skills.adapters.people_to_poster import SeriesRecord, _asset_from_path

_IMAGE_EXTENSIONS = (".webp", ".png", ".jpg", ".jpeg")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9_.-]+")

CACHE_POLICIES = {
    "reuse",
    "reuse_then_source",
    "reuse_then_source_then_placeholder",
    "refresh_source",
    "refresh_source_then_placeholder",
}


@dataclass(frozen=True)
class SeriesImageResolution:
    """Result object returned by resolve_series_image_assets."""

    assets: dict[str, ImageAsset]
    reused: list[str] = field(default_factory=list)
    downloaded: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    manifest_path: Path | None = None

class ImageDownloadRateLimited(RuntimeError):
    """Raised when the image host asks us to slow down."""

def _thumbnail_url(url: str, *, width: int = 768) -> str:
    """Ask Wikimedia Special:FilePath URLs for a smaller derivative image.

    This avoids downloading huge originals when a poster tile only needs a
    moderate-size portrait.
    """
    if "commons.wikimedia.org/wiki/Special:FilePath/" not in url:
        return url

    sep = "&" if "?" in url else "?"
    return f"{url}{sep}width={width}"

def safe_image_key(value: str) -> str:
    value = _SAFE_FILENAME.sub("_", str(value).strip())
    return value.strip("_") or "image"


def _candidate_paths(outdir: Path, image_key: str) -> list[Path]:
    stem = safe_image_key(image_key)
    return [outdir / f"{stem}{ext}" for ext in _IMAGE_EXTENSIONS]


def _find_cached(outdir: Path, image_key: str) -> Path | None:
    for path in _candidate_paths(outdir, image_key):
        if path.exists() and path.is_file():
            return path
    return None


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _center_crop_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.convert("RGB")
    w, h = image.size
    target_w, target_h = size
    target_ar = target_w / target_h
    current_ar = w / h

    if current_ar > target_ar:
        crop_w = int(h * target_ar)
        left = (w - crop_w) // 2
        box = (left, 0, left + crop_w, h)
    else:
        crop_h = int(w / target_ar)
        top = max(0, (h - crop_h) // 3)  # slight upward bias for portraits
        box = (0, top, w, top + crop_h)

    return image.crop(box).resize(size, Image.LANCZOS)


def _download_image(
    url: str,
    *,
    timeout: int,
    size: tuple[int, int],
    max_retries: int = 3,
    base_sleep: float = 5.0,
    max_sleep_before_abort: float = 60.0,
):
    """Download and normalize a source image for poster rendering.

    429 rate limits are temporary. They should stop/resume the cache-fill pass,
    not create placeholders.
    """
    from io import BytesIO
    import requests
    from PIL import Image, ImageOps, UnidentifiedImageError

    headers = {
        "User-Agent": "agentic-multimodal-demo/1.0 (local notebook)",
        "Accept": "image/*,*/*;q=0.8",
    }

    request_url = _thumbnail_url(url, width=max(size))

    for attempt in range(max_retries + 1):
        response = requests.get(
            request_url,
            timeout=timeout,
            headers=headers,
            allow_redirects=True,
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                sleep_seconds = float(retry_after)
            else:
                sleep_seconds = base_sleep * (2 ** attempt)

            if sleep_seconds > max_sleep_before_abort:
                raise ImageDownloadRateLimited(
                    f"Wikimedia returned HTTP 429 with Retry-After={sleep_seconds:.0f}s. "
                    f"Stop now and rerun later. URL: {response.url}"
                )

            if attempt < max_retries:
                print(
                    f"Wikimedia rate limited image download. "
                    f"Sleeping {sleep_seconds:.1f}s before retry {attempt + 1}/{max_retries}. "
                    f"URL: {response.url}"
                )
                time.sleep(sleep_seconds)
                continue

            raise ImageDownloadRateLimited(
                f"Wikimedia returned HTTP 429 after {max_retries + 1} attempts. "
                f"Last URL: {response.url}"
            )

        if response.status_code != 200:
            print("Image HTTP failure")
            print("  status:", response.status_code)
            print("  final url:", response.url)
            print("  preview:", response.text[:300])
            return None

        try:
            image = Image.open(BytesIO(response.content))
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            return _center_crop_resize(image, size)
        except UnidentifiedImageError:
            print("Could not decode image")
            print("  status:", response.status_code)
            print("  content-type:", response.headers.get("content-type"))
            print("  final url:", response.url)
            print("  bytes:", len(response.content))
            print("  preview:", response.text[:300])
            return None

    raise ImageDownloadRateLimited(f"Image download was rate limited. URL: {request_url}")


def _initials(name: str) -> str:
    parts = [part for part in re.split(r"\s+", name.strip()) if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _make_placeholder(name: str, *, size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, (238, 238, 238))
    draw = ImageDraw.Draw(image)
    border = 12
    draw.rectangle((border, border, size[0] - border, size[1] - border), outline=(170, 170, 170), width=4)

    initials = _initials(name)
    font_big = _load_font(max(28, size[0] // 5))
    font_small = _load_font(max(14, size[0] // 18))

    try:
        box = draw.textbbox((0, 0), initials, font=font_big)
        text_w, text_h = box[2] - box[0], box[3] - box[1]
    except Exception:
        text_w, text_h = draw.textsize(initials, font=font_big)

    draw.text(((size[0] - text_w) / 2, size[1] * 0.36 - text_h / 2), initials, fill=(80, 80, 80), font=font_big)

    display_name = name[:34] + ("..." if len(name) > 34 else "")
    try:
        box = draw.textbbox((0, 0), display_name, font=font_small)
        small_w = box[2] - box[0]
    except Exception:
        small_w = draw.textsize(display_name, font=font_small)[0]
    draw.text(((size[0] - small_w) / 2, size[1] * 0.68), display_name, fill=(80, 80, 80), font=font_small)
    return image


def _manifest_record(record: SeriesRecord, asset: ImageAsset, source: str) -> dict:
    return {
        "series_key": record.series_key,
        "record_id": record.record_id,
        "entity_id": record.entity_id,
        "image_key": record.image_key,
        "display_name": record.display_name,
        "subtitle": record.subtitle,
        "path": asset.path,
        "source": source,
        "image_url": record.image_url,
    }


def resolve_series_image_assets(
    records: Iterable[SeriesRecord],
    *,
    outdir: str | Path,
    cache_policy: str = "reuse_then_source_then_placeholder",
    size: tuple[int, int] = (512, 768),
    http_timeout: int = 15,
    manifest_name: str = "manifest.jsonl",
) -> SeriesImageResolution:
    """Resolve images for series records by stable image_key.

    cache_policy values:
    - "reuse": use only existing keyed files.
    - "reuse_then_source": reuse existing keyed files, then download record.image_url.
    - "reuse_then_source_then_placeholder": reuse, then source, then placeholder.
    - "refresh_source": ignore cached files and download source images only.
    - "refresh_source_then_placeholder": ignore cached files, source when possible,
      then create placeholders.

    The refresh policies are useful for one cleanup run after migrating away
    from ordinal/stale generated portrait caches.
    """
    if cache_policy not in CACHE_POLICIES:
        raise ValueError(f"unknown cache_policy={cache_policy!r}")

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    refresh = cache_policy.startswith("refresh_")
    allow_source = cache_policy in {
        "reuse_then_source",
        "reuse_then_source_then_placeholder",
        "refresh_source",
        "refresh_source_then_placeholder",
    }
    allow_placeholder = cache_policy in {
        "reuse_then_source_then_placeholder",
        "refresh_source_then_placeholder",
    }

    unique: dict[str, SeriesRecord] = {}
    for record in records:
        unique.setdefault(record.image_key, record)

    assets: dict[str, ImageAsset] = {}
    reused: list[str] = []
    downloaded: list[str] = []
    placeholders: list[str] = []
    missing: list[str] = []
    manifest_rows: list[dict] = []

    for image_key, record in unique.items():
        if not refresh:
            cached = _find_cached(outdir, image_key)
            if cached:
                asset = _asset_from_path(cached)
                assets[image_key] = asset
                reused.append(image_key)
                manifest_rows.append(_manifest_record(record, asset, "cache"))
                continue

        stem = safe_image_key(image_key)
        out_path = outdir / f"{stem}.webp"

        if allow_source and record.image_url:
            image = _download_image(
                record.image_url,
                timeout=http_timeout,
                size=size,
                max_retries=3,
                base_sleep=5.0,
            )
            if image is not None:
                image.save(out_path, format="WEBP", quality=92)
                asset = _asset_from_path(out_path)
                assets[image_key] = asset
                downloaded.append(image_key)
                manifest_rows.append(_manifest_record(record, asset, "source"))
                time.sleep(3.0)
                continue

        if allow_placeholder:
            image = _make_placeholder(record.display_name, size=size)
            image.save(out_path, format="WEBP", quality=92)
            asset = _asset_from_path(out_path)
            assets[image_key] = asset
            placeholders.append(image_key)
            manifest_rows.append(_manifest_record(record, asset, "placeholder"))
            continue

        missing.append(image_key)

    manifest_path = outdir / manifest_name
    with manifest_path.open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return SeriesImageResolution(
        assets=assets,
        reused=reused,
        downloaded=downloaded,
        placeholders=placeholders,
        missing=missing,
        manifest_path=manifest_path,
    )
