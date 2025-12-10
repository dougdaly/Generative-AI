from __future__ import annotations
from typing import Optional, Tuple
import os, math, hashlib
from PIL import Image, ImageDraw, ImageFont, ImageOps
from dataclasses import dataclass
import io, hashlib, requests
_MERC_MAX = 85.05112878


# ------------ helpers -----------------------------------------------------------
# ---- 1) pure geo projection (no pixels) ----
def _mercator_xy(lon: float, lat: float) -> tuple[float, float]:
    # clamp latitude to avoid infinities (~85 deg)
    lat = max(min(lat, _MERC_MAX), -_MERC_MAX)
    x = lon
    y = (180.0/math.pi) * math.log(math.tan(math.pi/4.0 + (lat*math.pi/180.0)/2.0))
    return x, y

def _equirect_xy(lon: float, lat: float) -> tuple[float, float]:
    return lon, lat

def _extract_route_meta(spec):
    """
    Try to read route metadata from spec.meta if present.
    Returns (route_waypoints, route_bbox) or (None, None).

    route_waypoints expected as list of (lat, lon)
    route_bbox expected as (min_lat, max_lat, min_lon, max_lon)
    """
    meta = getattr(spec, "meta", None)
    if not isinstance(meta, dict):
        return None, None

    wps = meta.get("route_waypoints")
    bbox = meta.get("bbox")
    return wps, bbox

def _merc_y(lat: float) -> float:
    lat = max(min(lat, _MERC_MAX), -_MERC_MAX)
    rad = math.radians(lat)
    return math.log(math.tan(math.pi / 4.0 + rad / 2.0))

def _inv_merc_y(y: float) -> float:
    rad = 2.0 * math.atan(math.exp(y)) - math.pi / 2.0
    return math.degrees(rad)

def _pad_bbox_to_aspect(
    west: float, south: float, east: float, north: float,
    *,
    width_px: int, height_px: int,
    margin_px: int = 0,
    lat_cap: float | None = 70.0,
):
    Wm = max(1, width_px  - 2 * margin_px)
    Hm = max(1, height_px - 2 * margin_px)
    canvas_ratio = Wm / Hm

    # ---- Mercator-space spans ----
    x_span = max(1e-9, math.radians(east - west))  # ✅ fix
    y_s = _merc_y(south)
    y_n = _merc_y(north)
    y_span = max(1e-9, y_n - y_s)

    current_ratio = x_span / y_span

    # Too wide → pad latitude in Mercator y
    if current_ratio > canvas_ratio:
        target_y_span = x_span / canvas_ratio
        extra = target_y_span - y_span
        pad = extra / 2.0

        new_y_s = y_s - pad
        new_y_n = y_n + pad

        south = _inv_merc_y(new_y_s)
        north = _inv_merc_y(new_y_n)

        if lat_cap is not None:
            south = max(south, -lat_cap)
            north = min(north,  lat_cap)

    # Too tall → pad longitude in degrees (via radians math)
    elif current_ratio < canvas_ratio:
        target_x_span = y_span * canvas_ratio
        extra = target_x_span - x_span
        pad = extra / 2.0

        pad_deg = math.degrees(pad)  # ✅ fix
        west -= pad_deg
        east += pad_deg

        west = max(-180.0, west)
        east = min(180.0, east)

    return west, south, east, north

# ---- 2) viewport projector (pixels) ----

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

def _draw_route(draw, proj, route_waypoints, *, upscale=1):
    """
    Draw a route polyline from waypoints.
    route_waypoints: list[Waypoint]
    """
    if not route_waypoints or len(route_waypoints) < 2:
        return

    pts = []
    for wp in route_waypoints:
        try:
            x, y = proj.project(wp.lon, wp.lat)  # NOTE: projector expects lon,lat
            pts.append((x, y))
        except Exception:
            continue

    if len(pts) >= 2:
        # Keep it simple. A dark-ish line reads well over pastel fills.
        # Avoid fancy styling for v1.
        width = max(3, int(5 * upscale))
        draw.line(pts, fill=(10, 30, 80), width=width)


def _paint_basemap(canvas, draw, proj, upscale, *, fill_countries: bool = True):
    from agentic_multimodal.skills.data.natural_earth import iter_admin0_polys

    W, H = canvas.size
    sea = (198, 221, 247)
    draw.rectangle([0, 0, W, H], fill=sea)

    # country fills
    for feat in iter_admin0_polys(proj.bbox) or []:
        fill = _pastel_fill_for(feat["name"])
        for poly in feat["polys"]:
            outer_px = [proj.project(lon, lat) for (lon, lat) in poly["outer"]]
            if fill_countries:
                draw.polygon(outer_px, fill=fill)
            # holes
            for hole in poly["holes"]:
                hole_px = [proj.project(lon, lat) for (lon, lat) in hole]
                draw.polygon(hole_px, fill=sea)

    border = (150, 161, 173)
    for feat in iter_admin0_polys(proj.bbox) or []:
        for poly in feat["polys"]:
            outer_px = [proj.project(lon, lat) for (lon, lat) in poly["outer"]]
            draw.line(outer_px + outer_px[:1], fill=border, width=max(1, upscale))



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

def _round_rect(im: Image.Image, *, size_px: int, radius_px: int) -> Image.Image:
    """Resize image to square and apply rounded-rect alpha mask."""
    sz = max(8, int(size_px))
    r  = max(0, int(radius_px))

    im = im.convert("RGBA").resize((sz, sz), Image.Resampling.LANCZOS)

    mask = _round_mask(sz, sz, r)  # you already have _round_mask
    im.putalpha(mask)
    return im


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
            marker_px=84, label_font_px=32, 
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
            fill_countries: bool = True,
            title_scale: float = 1.5,
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

    title_font_px = max(label_font_px + 4, int(label_font_px * title_scale))
    title_font = ImageFont.truetype(_resolve_font(), title_font_px)
    
    route_waypoints, route_bbox = _extract_route_meta(spec)

    if route_bbox:
        # route_bbox is (min_lat, max_lat, min_lon, max_lon)
        min_lat, max_lat, min_lon, max_lon = route_bbox
        west, south, east, north = (min_lon, min_lat, max_lon, max_lat)
    else:
        (west, south, east, north) = _lonlat_bbox(spec.markers)
    # Pad the bounding box to match aspect ratio
    west, south, east, north = _pad_bbox_to_aspect(
        west, south, east, north,
        width_px=W, height_px=H,
        margin_px=margin,
        lat_cap=70.0,
    )
    proj = ViewportProjector(
        west, south, east, north,
        width=W, height=H, margin=margin, projection="mercator"
    )
    _paint_basemap(canvas, draw, proj, upscale, fill_countries=fill_countries)
    if route_waypoints:
        _draw_route(draw, proj, route_waypoints, upscale=upscale)

    # Title
    title = getattr(spec, "title", None) or getattr(spec, "region", "Map")

    tb = draw.textbbox((0, 0), title, font=title_font)
    tw = tb[2] - tb[0]
    th = tb[3] - tb[1]

    draw.text(((W - tw) // 2, 8), title, font=title_font, fill="#1f2d3a")

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
        # Seems None is returned based on the logic
        if not fetch_images: # fetch_images is not defined ???
            return None
        try:
            import requests
            from io import BytesIO
            r = requests.get(url, timeout=fetch_timeout)
            r.raise_for_status()
            im = Image.open(BytesIO(r.content)).convert("RGBA")
            im.thumbnail((pick_thumb_px, pick_thumb_px), Image.Resampling.LANCZOS) # pick_thumb_px is not defined
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
