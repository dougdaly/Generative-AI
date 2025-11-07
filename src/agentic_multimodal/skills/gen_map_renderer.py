from __future__ import annotations
from typing import Optional, Tuple
import os, math, hashlib
from PIL import Image, ImageDraw, ImageFont

# ------------ helpers -----------------------------------------------------------
from PIL import Image, ImageDraw, ImageFont

def _pastel_fill_for(name: str) -> tuple[int,int,int]:
    # stable pastel color per country
    import hashlib
    h = int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:6], 16)
    r = 160 + (h >> 16) % 80
    g = 160 + (h >> 8)  % 80
    b = 160 + (h      ) % 80
    return (r, g, b)

def _paint_basemap(canvas, draw, bbox, W, H, margin, upscale):
    try:
        from agentic_multimodal.skills.data.natural_earth import iter_admin0_polys
    except Exception:
        return

    # Sea fill first
    sea = (198, 221, 247)           # light blue
    draw.rectangle([0,0,W,H], fill=sea)

    # Country fills with holes
    for feat in iter_admin0_polys(bbox) or []:
        fill = _pastel_fill_for(feat["name"])
        for poly in feat["polys"]:
            outer_px = [_project(lon, lat, bbox, W, H, margin) for (lon,lat) in poly["outer"]]
            # Fill exterior
            draw.polygon(outer_px, fill=fill)
            # Punch holes by painting sea inside them
            for hole in poly["holes"]:
                hole_px = [_project(lon, lat, bbox, W, H, margin) for (lon,lat) in hole]
                draw.polygon(hole_px, fill=sea)

    # Thin border stroke
    border = (150, 161, 173)
    for feat in iter_admin0_polys(bbox) or []:
        for poly in feat["polys"]:
            outer_px = [_project(lon, lat, bbox, W, H, margin) for (lon,lat) in poly["outer"]]
            draw.line(outer_px, fill=border, width=max(1, upscale))
            for hole in poly["holes"]:
                hole_px = [_project(lon, lat, bbox, W, H, margin) for (lon,lat) in hole]
                draw.line(hole_px, fill=border, width=max(1, upscale))

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

def _project(lon, lat, bbox, w, h, margin):
    west, south, east, north = bbox
    # Plate Carree
    x = (lon - west) / (east - west + 1e-9)
    y = 1.0 - (lat - south) / (north - south + 1e-9)
    x_px = int(margin + x * (w - 2 * margin))
    y_px = int(margin + y * (h - 2 * margin))
    return x_px, y_px

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
               max_labels=None) -> str:

    upscale = 2  # supersample factor
    W0, H0 = size
    W, H = W0*upscale, H0*upscale
    margin *= upscale
    marker_px *= upscale
    label_font_px *= upscale

    canvas = Image.new("RGB", (W, H), (238,245,251))  # will be overpainted by _paint_basemap
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(_resolve_font(), label_font_px)

    bbox = _lonlat_bbox(spec.markers)
    _paint_basemap(canvas, draw, bbox, W, H, margin, upscale)
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
    for m in spec.markers:
        if m.lon is None or m.lat is None:
            continue
        x, y = _project(m.lon, m.lat, bbox, W, H, margin)

        # --- flag de-overlap ---
        def _too_close(pts, x, y, min_d):
            for (px, py) in pts:
                if (px - x)**2 + (py - y)**2 < (min_d**2):
                    return True
            return False

        place_flag = not _too_close(used_for_flags, x, y, min_flag_separation_px)
        im = _load_marker_image(m, cache_dir, marker_px) if place_flag else None

        if im is None:
            # draw pin if we skipped the flag or couldn't load
            r = max(2, marker_px // 8)
            draw.ellipse([(x-r, y-r), (x+r, y+r)], fill="#666c7a", outline=None)
        else:
            canvas.paste(im, (int(x - im.width//2), int(y - im.height//2)), im)
            used_for_flags.append((x, y))

        # --- label de-overlap ---
        label = ""
        if show_labels and show_country_names:
            label = (m.label or "").strip()

        if show_labels and show_capital_names:
            cap = (m.meta or {}).get("capital_name")
            if cap:
                label = f"{label}\n{cap}" if label else cap

        if show_labels and label:
            # simple screen-space declutter
            if not _too_close(used_for_labels, x, y, min_label_separation_px):
                if max_labels is None or labels_drawn < max_labels:
                    bbox_t = draw.textbbox((0,0), label, font=font)
                    lw, lh = bbox_t[2]-bbox_t[0], bbox_t[3]-bbox_t[1]
                    lx, ly = int(x - lw/2), int(y + marker_px*0.55)
                    draw.text((lx, ly), label, font=font, fill="black",
                            stroke_width=3, stroke_fill="white")
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
