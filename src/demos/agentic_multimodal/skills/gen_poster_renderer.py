from __future__ import annotations
from math import ceil, sqrt
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont
from agentic_multimodal.schemas.artifacts import PosterSpec, PosterItem
from agentic_multimodal.skills.image_gen import resolve_font 


import os
from pathlib import Path
from typing import Tuple, Optional

from agentic_multimodal.schemas.artifacts import PosterSpec


def compose_poster_spec(
    spec: PosterSpec,
    *,
    tile_size: Tuple[int,int] = (512, 768),   # image area per tile; label draws below it
    margin: int = 40,
    gutter: int = 24,
    base_font_path: str | None = "assets/fonts/Inter-SemiBold.ttf",
    base_font_px: int = 26,
    caption_scale: float = 2.0,
    line_gap_px: int = 6,
    stroke_width_px: int = 3,
    outpath: str | None = None,
    out_format: str = "WEBP",
    out_quality: int = 80,
    max_long_side: int | None = 4096,
    max_megapixels: float | None = None,
):
    img_w, img_h = tile_size
    n = len(spec.items)
    cols = max(1, spec.grid_cols)
    rows = ceil(n / cols)

    # caption height estimate
    line_h = int(base_font_px * caption_scale)
    caption_h = line_h * 2 + int(line_gap_px * caption_scale)

    W = margin*2 + cols*img_w + (cols-1)*gutter
    H = margin*2 + rows*(img_h + caption_h) + (rows-1)*gutter + 0
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)

    # font
    font_path = resolve_font(base_font_path)
    def draw_centered_multiline(center_xy, text: str):
        lines = text.split("\n")
        fsize = max(1, int(base_font_px * caption_scale))
        gap   = max(1, int(line_gap_px * caption_scale))
        sw    = max(1, int(stroke_width_px))
        font  = ImageFont.truetype(font_path, fsize)
        widths, heights = [], []
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font, stroke_width=sw)
            widths.append(bbox[2]-bbox[0])
            heights.append(bbox[3]-bbox[1])
        block_w = max(widths) if widths else 0
        block_h = sum(heights) + gap*(len(lines)-1 if lines else 0)
        cx, cy = center_xy
        x0, y0 = int(cx - block_w/2), int(cy - block_h/2)
        y = y0
        for line, h in zip(lines, heights):
            draw.text((x0, y), line, font=font, fill=(0,0,0),
                      stroke_width=sw, stroke_fill=(255,255,255), align="center")
            y += h + gap

    # tiles
    k = 0
    for r in range(rows):
        for c in range(cols):
            if k >= n: break
            item: PosterItem = spec.items[k]
            tx = margin + c*(img_w + gutter)
            ty = margin + r*(img_h + caption_h + gutter)

            im = Image.open(item.image.path).convert("RGB")
            if im.size != (img_w, img_h):
                im = im.resize((img_w, img_h), Image.Resampling.LANCZOS)
            canvas.paste(im, (tx, ty))

            caption_center = (tx + img_w//2, ty + img_h + caption_h//2)
            draw_centered_multiline(caption_center, item.label)
            k += 1

    # optional downscale
    if max_long_side or max_megapixels:
        CW, CH = canvas.size
        scale = 1.0
        if max_long_side:
            scale = min(scale, max_long_side / max(CW, CH))
        if max_megapixels:
            target = max_megapixels * 1_000_000
            scale = min(scale, (target / (CW*CH))**0.5)
        if scale < 1.0:
            new_size = (int(CW*scale), int(CH*scale))
            canvas = canvas.resize(new_size, Image.Resampling.LANCZOS)

    if outpath:
        fmt = out_format.upper()
        if fmt == "WEBP":
            canvas.save(outpath, format="WEBP", quality=out_quality, method=6)
        elif fmt == "JPEG":
            canvas.save(outpath, format="JPEG", quality=out_quality, subsampling="4:2:0", optimize=True, progressive=True)
        elif fmt == "PNG":
            canvas.save(outpath, format="PNG", optimize=True, compress_level=9)
        else:
            canvas.save(outpath)
    return canvas


def render_poster(
    spec: PosterSpec,
    *,
    outdir: str = "artifacts/posters",
    outpath: str | None = None,
    out_format: str = "WEBP",
    out_quality: int = 80,
    **kw,
) -> str:
    """
    Wrapper that ensures a saved image + returns the output path.
    compose_poster_spec() builds the PIL canvas; we give it an outpath.
    """
    from pathlib import Path

    Path(outdir).mkdir(parents=True, exist_ok=True)

    if outpath is None:
        # cheap safe filename from title
        safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in (spec.title or "poster"))
        safe = "_".join(safe.strip().split())[:80] or "poster"
        outpath = str(Path(outdir) / f"{safe}.{out_format.lower()}")

    # Compose (and save if compose_poster_spec honors outpath)
    canvas = compose_poster_spec(
        spec,
        outpath=outpath,
        out_format=out_format,
        out_quality=out_quality,
        **kw,
    )

    # If compose_poster_spec doesn't save internally, this guarantees it.
    if not Path(outpath).exists():
        fmt = out_format.upper()
        if fmt == "JPG":
            fmt = "JPEG"
        canvas.save(outpath, format=fmt, quality=out_quality)

    return outpath
