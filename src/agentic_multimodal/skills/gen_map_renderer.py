from __future__ import annotations
from typing import Optional, Tuple
import os, math, hashlib
from PIL import Image, ImageDraw, ImageFont, ImageOps
from dataclasses import dataclass
from math import log, tan, pi
import io, hashlib, requests


# ------------ helpers -----------------------------------------------------------
# ---- 1) pure geo projection (no pixels) ----
def _mercator_xy(lon: float, lat: float) -> tuple[float, float]:
    # clamp latitude to avoid infinities (~85 deg)
    lat = max(min(lat, 85.05112878), -85.05112878)
    x = lon
    y = (180.0/pi) * log(tan(pi/4.0 + (lat*pi/180.0)/2.0))
    return x, y

def _equirect_xy(lon: float, lat: float) -> tuple[float, float]:
    return lon, lat

# ---- 2) viewport projector (pixels) ----
# skills/gen_map_renderer.py (or wherever your projector lives)
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class ViewportProjector:
    west: float; south: float; east: float; north: float
    width: int; height: int; margin: int = 20
    projection: str = "mercator"  # "mercator" | "equirect"

    def __post_init__(self):
        # expose bbox and inner drawable area
        object.__setattr__(self, "bbox", (self.west, self.south, self.east, self.north))
        Wm = max(1, self.width  - 2*self.margin)
        Hm = max(1, self.height - 2*self.margin)
        object.__setattr__(self, "_Wm", Wm)
        object.__setattr__(self, "_Hm", Hm)

        if self.projection == "mercator":
            # clamp to Mercator safe range
            south = max(min(self.south, 85.05112878), -85.05112878)
            north = max(min(self.north, 85.05112878), -85.05112878)
            def m(lat_deg: float) -> float:
                lat = math.radians(max(min(lat_deg, 85.05112878), -85.05112878))
                return math.log(math.tan(math.pi/4.0 + lat/2.0))
            yS, yN = m(south), m(north)
            object.__setattr__(self, "_mSouth", yS)
            object.__setattr__(self, "_mNorth", yN)
        else:
            # equirectangular: linear lat
            object.__setattr__(self, "_mSouth", math.radians(self.south))
            object.__setattr__(self, "_mNorth", math.radians(self.north))

    def project(self, lon: float, lat: float) -> tuple[int, int]:
        """
        lon,lat in degrees → (x,y) pixels.
        """
        # normalize lon to bbox span if needed
        L = self.east - self.west
        x_norm = (lon - self.west) / L

        if self.projection == "mercator":
            # top at north (smaller y), bottom at south
            def m(lat_deg: float) -> float:
                lat = math.radians(max(min(lat_deg, 85.05112878), -85.05112878))
                return math.log(math.tan(math.pi/4.0 + lat/2.0))
            y_lat = m(lat)
            y_norm = (self._mNorth - y_lat) / (self._mNorth - self._mSouth)
        else:  # equirectangular
            y_lat = math.radians(lat)
            y_norm = (math.radians(self.north) - y_lat) / (math.radians(self.north) - math.radians(self.south))

        x_px = self.margin + int(round(x_norm * self._Wm))
        y_px = self.margin + int(round(y_norm * self._Hm))
        return x_px, y_px

def _fetch_image_cached(url: str, cache_dir: str, timeout: int = 8, retries: int = 1) -> Image.Image | None:
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".bin"
    path = os.path.join(cache_dir, key)

    # cache hit
    if os.path.isfile(path):
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            pass  # fall through to re-download

    # download
    for _ in range(retries + 1):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                im.save(path)  # simple cache
                return im
        except Exception:
            continue
    return None

def _circle_thumb(im: Image.Image, diameter: int) -> tuple[Image.Image, Image.Image]:
    d = max(8, int(diameter))  # guard tiny
    im = im.resize((d, d), Image.Resampling.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d-1, d-1), fill=255)
    return im, mask


def _measure_text(draw, text, font):
    bbox = draw.multiline_textbbox((0,0), text, font=font, spacing=2)
    return bbox[0], bbox[1], bbox[2]-bbox[0], bbox[3]-bbox[1]

def _draw_text(draw, text, xy, font):
    draw.multiline_text(
        xy, text, font=font, fill="black", spacing=2,
        stroke_width=3, stroke_fill="white",
        align="center"
    )

def _too_close(used_xy: list[tuple[int, int]], x: int, y: int, min_sep_px: int) -> bool:
    """Return True if (x,y) is within min_sep_px of any prior (ux,uy)."""
    if not used_xy or min_sep_px <= 0:
        return False
    r2 = min_sep_px * min_sep_px
    for ux, uy in used_xy:
        dx = x - ux
        dy = y - uy
        if dx*dx + dy*dy <= r2:
            return True
    return False


def _raster_url(url: str, timeout=6.0):
    if not url: return None
    if url.lower().endswith(".svg"):
        return None  # optional: rasterize via cairosvg if you want
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None

def _round_mask(w, h, radius):
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle((0, 0, w-1, h-1), radius=radius, fill=255)
    return m

def _circle_mask(d):
    m = Image.new("L", (d, d), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d-1, d-1), fill=255)
    return m

def _pastel_fill_for(name: str) -> tuple[int,int,int]:
    # stable pastel color per country
    import hashlib
    h = int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:6], 16)
    r = 160 + (h >> 16) % 80
    g = 160 + (h >> 8)  % 80
    b = 160 + (h      ) % 80
    return (r, g, b)

def _paint_basemap(canvas, draw, proj, upscale):
    from agentic_multimodal.skills.data.natural_earth import iter_admin0_polys

    W, H = canvas.size
    sea = (198, 221, 247)
    draw.rectangle([0, 0, W, H], fill=sea)

    # country fills
    for feat in iter_admin0_polys(proj.bbox) or []:
        fill = _pastel_fill_for(feat["name"])
        for poly in feat["polys"]:
            outer_px = [proj.project(lon, lat) for (lon, lat) in poly["outer"]]
            draw.polygon(outer_px, fill=fill)
            for hole in poly["holes"]:
                hole_px = [proj.project(lon, lat) for (lon, lat) in hole]
                draw.polygon(hole_px, fill=sea)

    border = (150, 161, 173)
    for feat in iter_admin0_polys(proj.bbox) or []:
        for poly in feat["polys"]:
            outer_px = [proj.project(lon, lat) for (lon, lat) in poly["outer"]]
            draw.line(outer_px + outer_px[:1], fill=border, width=max(1, upscale))
            for hole in poly["holes"]:
                hole_px = [proj.project(lon, lat) for (lon, lat) in hole]
                draw.line(hole_px + hole_px[:1], fill=border, width=max(1, upscale))


def _fetch_url_bytes(url: str, timeout: int = 15) -> Optional[bytes]:
    try:
        import requests
        r = requests.get(url, timeout=timeout, headers={"User-Agent":"agentic-multimodal/1.0"})
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None

def _wikimedia_png_from_svg_url(svg_url: str, px: int) -> Optional[bytes]:
    # Works even without cairosvg by letting Commons rasterize the SVG.
    if "commons.wikimedia.org" not in svg_url:
        return None
    try:
        import requests
        # Convert /wiki/File:Foo.svg -> /wiki/Special:FilePath/Foo.svg?width=PX
        if "/wiki/File:" in svg_url:
            filename = svg_url.rsplit("/wiki/File:", 1)[-1]
            url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename}?width={px}"
        elif "/File:" in svg_url:
            filename = svg_url.rsplit("/File:", 1)[-1]
            url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename}?width={px}"
        else:
            # Many Wikidata P41 URLs are direct upload URLs; server accepts ?width=
            url = svg_url + (f"?width={px}" if "?" not in svg_url else f"&width={px}")
        r = requests.get(url, timeout=15, headers={"User-Agent":"agentic-multimodal/1.0"})
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        return None
    return None


def _ensure_dir(p: str) -> None:
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]

def _resolve_font():
    # reuse your resolver if you prefer: from skills.image_gen import resolve_font
    candidates = [
        "assets/fonts/Inter-SemiBold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "DejaVuSans.ttf",
    ]
    for c in candidates:
        try:
            ImageFont.truetype(c, 24)
            return c
        except Exception:
            continue
    raise FileNotFoundError("No usable TTF font found for map labels.")

def _lonlat_bbox(markers):
    lons = [m.lon for m in markers if m.lon is not None]
    lats = [m.lat for m in markers if m.lat is not None]
    if not lons or not lats:
        # Default world bbox
        return (-180.0, -85.0, 180.0, 85.0)
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)
    # pad a bit
    pad_x = max(2.0, (east - west) * 0.08)
    pad_y = max(1.0, (north - south) * 0.08)
    return (west - pad_x, south - pad_y, east + pad_x, north + pad_y)

def _rasterize_svg_to_png(svg_bytes: bytes, out_png_path: str, px: int) -> Optional[str]:
    try:
        import cairosvg
        _ensure_dir(out_png_path)
        cairosvg.svg2png(bytestring=svg_bytes, write_to=out_png_path, output_width=px, output_height=px)
        return out_png_path
    except Exception:
        return None

def _fetch_url_bytes(url: str) -> Optional[bytes]:
    # Try your service fetcher if available; else bail.
    try:
        from agentic_multimodal.services.io_web_fetcher import fetch_bytes
        return fetch_bytes(url, timeout=15)
    except Exception:
        return None

def _load_marker_image(marker, cache_dir: str, marker_px: int) -> Optional[Image.Image]:
    # 1) local asset path
    if getattr(marker, "image", None) and getattr(marker.image, "path", None):
        try:
            im = Image.open(marker.image.path).convert("RGBA")
            return im.resize((marker_px, marker_px), Image.Resampling.LANCZOS)
        except Exception:
            pass

    url = (marker.meta or {}).get("flag_svg_url")
    if url:
        tag = _hash(url) + f"_{marker_px}"
        png_path = os.path.join(cache_dir, f"{tag}.png")

        # 2) try cairosvg if SVG
        if url.lower().endswith(".svg"):
            svgb = _fetch_url_bytes(url)
            if svgb:
                png = _rasterize_svg_to_png(svgb, png_path, marker_px)
                if png:
                    try:
                        return Image.open(png).convert("RGBA")
                    except Exception:
                        pass
            # 3) server-side rasterization fallback
            png_bytes = _wikimedia_png_from_svg_url(url, marker_px)
            if png_bytes:
                try:
                    from io import BytesIO
                    im = Image.open(BytesIO(png_bytes)).convert("RGBA")
                    im.save(png_path)  # cache
                    return im
                except Exception:
                    pass
        # 4) direct raster URL
        if any(url.lower().endswith(ext) for ext in (".png",".jpg",".jpeg",".webp")):
            b = _fetch_url_bytes(url)
            if b:
                try:
                    from io import BytesIO
                    im = Image.open(BytesIO(b)).convert("RGBA")
                    return im.resize((marker_px, marker_px), Image.Resampling.LANCZOS)
                except Exception:
                    pass
    return None



# ---- PUBLIC API -------------------------------------------------------------
def render_map(spec, *, size=(2000,1200), margin=40,
            marker_px=84, label_font_px=20,
            outdir="artifacts/maps",
            show_labels=True,
            show_country_names=True,
            show_capital_names=False,
            min_flag_separation_px=36,
            min_label_separation_px=48,
            max_labels: int|None =None,
            show_pick_images: bool=True,
            pick_image_size_px=44,
            show_flag_markers=False,
            flag_marker_size_px=40,
            flag_corner_radius_px=6,
            label_offset_px=8,
            fetch_timeout=8.0,          
            fetch_retries=1,            
            cache_dir=None,     
        ) -> str:

    if cache_dir is None:
        cache_dir = os.path.join(outdir, "_http_cache")
    os.makedirs(cache_dir, exist_ok=True)

    upscale = 2  # supersample factor
    W0, H0 = size
    W, H = W0*upscale, H0*upscale
    margin *= upscale
    marker_px *= upscale
    label_font_px *= upscale

    canvas = Image.new("RGB", (W, H), (238,245,251))  # will be overpainted by _paint_basemap
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(_resolve_font(), label_font_px)

    (west, south, east, north) = _lonlat_bbox(spec.markers)
    proj = ViewportProjector(west, south, east, north, width=W, height=H, margin=margin, projection="mercator")
    _paint_basemap(canvas, draw, proj, upscale)

    # Title
    title = getattr(spec, "title", None) or getattr(spec, "region", "Map")
    tw, th = draw.textbbox((0,0), title, font=font)[2:]
    draw.text(((W - tw)//2, 8), title, font=font, fill="#1f2d3a")

    # Marker cache dir
    cache_dir = os.path.join(outdir, "_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Draw markers
    used_for_flags = []
    used_for_labels = []
    labels_drawn = 0
    def _fetch_thumb(url: str) -> Image.Image | None:
        if not url:
            return None
        os.makedirs(cache_dir, exist_ok=True)
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]
        path = os.path.join(cache_dir, key + ".png")
        if os.path.exists(path):
            try:
                return Image.open(path).convert("RGBA")
            except Exception:
                pass
        if not fetch_images:
            return None
        try:
            import requests
            from io import BytesIO
            r = requests.get(url, timeout=fetch_timeout)
            r.raise_for_status()
            im = Image.open(BytesIO(r.content)).convert("RGBA")
            im.thumbnail((pick_thumb_px, pick_thumb_px), Image.Resampling.LANCZOS)
            im.save(path, "PNG", optimize=True)
            return im
        except Exception:
            return None

    # --- draw markers ---
    for m in spec.markers:
        x, y = proj.project(m.lon, m.lat)

        used_portrait = False
        used_flag = False
        meta = m.meta or {}

        # ---- 1) Portrait (prefer local path; then URL) ----
        im = None
        if show_pick_images:
            img_path = meta.get("pick_image_path")  # must be a string now
            if img_path and os.path.exists(img_path):
                im = Image.open(img_path).convert("RGBA")
            else:
                img_url = meta.get("pick_image_url")
                if img_url:
                    im = _fetch_image_cached(img_url, cache_dir, timeout=fetch_timeout, retries=fetch_retries)

        if im:
            # circular thumb; diameter = pick_image_size_px
            thumb, mask = _circle_thumb(im, int(pick_image_size_px)*upscale)
            tx = int(x - thumb.width  / 2)
            ty = int(y - thumb.height / 2)
            canvas.paste(thumb, (tx, ty), mask)
            used_portrait = True

        # ---- 2) Flag box (only if no portrait) ----
        if not used_portrait and show_flag_markers:
            flag_url = meta.get("flag_url")
            if flag_url:
                fl = _fetch_image_cached(flag_url, cache_dir, timeout=fetch_timeout, retries=fetch_retries)
                if fl:
                    flag_box = _round_rect(fl, size_px=int(flag_marker_size_px), radius_px=int(flag_corner_radius_px))
                    fx = int(x - flag_box.width  / 2)
                    fy = int(y - flag_box.height / 2)
                    # use alpha channel if present
                    canvas.paste(flag_box, (fx, fy), flag_box.split()[-1] if flag_box.mode == "RGBA" else None)
                    used_flag = True

        # ---- 3) Tiny dot (only if neither portrait nor flag) ----
        if not used_portrait and not used_flag:
            r_dot = max(2, int(marker_px / 3))
            draw.ellipse((x - r_dot, y - r_dot, x + r_dot, y + r_dot), fill=(38,132,255))

        # ---- Label placement: nudge based on what we drew ----
        if show_labels:
            label = (m.label or "").strip()
            if label and not _too_close(used_for_labels, x, y, min_label_separation_px):
                # baseline offset: dot
                dy = 6 + (marker_px // 2)
                # bump if portrait or flag is present
                if used_portrait:
                    dy = 6 + int(pick_image_size_px / 2)
                elif used_flag:
                    dy = 6 + int(flag_marker_size_px / 2)

                bx, by, bw, bh = _measure_text(draw, label, font)
                lx, ly = int(x - bw/2), int(y + dy)
                _draw_text(draw, label, (lx, ly), font)
                used_for_labels.append((x, y))
                labels_drawn += 1


    # Output
    safe_title = "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in title)
    if not safe_title.strip():
        safe_title = (getattr(spec, "region", None) or "map")
    out_path = os.path.join(outdir, f"{safe_title}.png")
    _ensure_dir(out_path)
    # Downscale with antialias
    out = canvas.resize((W0, H0), Image.Resampling.LANCZOS)
    out.save(out_path, format="PNG", optimize=True)
    # attach to spec
    try:
        spec.path = out_path
    except Exception:
        pass
    return out_path
