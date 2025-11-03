from math import ceil, sqrt
from PIL import Image, ImageDraw, ImageFont
import re, os
import torch

# Define prompts for individuals
# Add prompt hint based on year
def era_hint(year):
    y = int(year) if (year and year.isdigit()) else None
    if not y: return ""
    if y < 1500: return "medieval attire"
    if y < 1700: return "Renaissance attire"
    if y < 1800: return "18th-century attire, powdered wig"
    if y < 1900: return "19th-century attire"
    if y < 1950: return "early 20th-century attire"
    return "modern attire"

def person_prompt(name, year=None):
    prompt = f"""cartoon portrait, {name}, solo, single subject, one person,
                bust-length, centered, cropped at shoulders, clean background, flat shading, flat colors, minimal lines""".strip()
    neg_prompt = """group, crowd, second person, extra face, extra head, duplicate, twins,
                    reflection, mirror, collage, poster wall, background portrait, statues,
                    disembodied face, body doubles, text, watermark, logo, hands, full body""".strip()
    if year is not None:
        prompt += ","+era_hint(year)
    return prompt, neg_prompt


# Generate collection of portraits
def resolve_font(preferred: str | None = None):
    """
    Return a path or font name that ImageFont.truetype can open.
    Tries: user-supplied path → common system fonts → Pillow's bundled DejaVu.
    """
    # 0) user-supplied path, if valid
    if preferred and os.path.isfile(preferred):
        return preferred

    # 1) common system fonts (macOS / Linux / Windows)
    candidates = [
        # macOS
        "/Library/Fonts/Arial.ttf",
        "/Library/Fonts/HelveticaNeue.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    # 2) Pillow ships DejaVuSans; most installs can resolve it by name
    try:
        # This works if PIL packaged fonts are on the font path
        ImageFont.truetype("DejaVuSans.ttf", size=10)
        return "DejaVuSans.ttf"
    except Exception:
        pass

    # 3) Absolute worst-case: raise a helpful error
    raise FileNotFoundError(
        "No usable TTF font found. Put a .ttf in assets/fonts/ and set base_font_path to it."
    )


def _safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", s)
    return s.strip("_")

def batch_generate_portraits(
    series_payload: dict,
    outdir: str = "out/series",
    steps: int = 25,
    scale: float = 6.5,
    size: tuple[int,int] = (512, 768),
    seed: int | None = 1337,     # set to None for non-deterministic
    skip_existing: bool = True,
):
    os.makedirs(outdir, exist_ok=True)
    pipe, device = get_sdxl()

    generator = None
    if seed is not None:
        generator = torch.Generator(device=device)
        generator.manual_seed(seed)

    paths = []
    W, H = size  # (width, height)

    for i, item in enumerate(series_payload.get("items", []), 1):
        name  = item.get("name", f"item_{i}")
        prompt = item.get("prompt")
        neg_prompt = item.get("neg_prompt")

        fname = f"{i:03d}_{_safe_filename(name)}.png"
        fpath = os.path.join(outdir, fname)
        paths.append(fpath)

        if skip_existing and os.path.exists(fpath):
            continue

        img = pipe(
            prompt=prompt,
            negative_prompt=neg_prompt,
            num_inference_steps=steps,
            guidance_scale=scale,
            width=W,
            height=H,
            generator=generator
        ).images[0]
        img.save(fpath)

    return paths



from PIL import Image, ImageDraw, ImageFont

def draw_centered_multiline(
    canvas: Image.Image,
    text_lines: list[str],
    center_xy: tuple[int,int],
    base_font_path: str | None = None,  # can be None now
    base_font_px: int = 28,
    fill=(0,0,0),
    stroke_fill=(255,255,255),
    stroke_width_px: int = 2,
    line_gap_px: int = 6,
    scale: float = 1.0,
):
    draw = ImageDraw.Draw(canvas)
    fsize = max(1, int(base_font_px * scale))
    gap   = max(1, int(line_gap_px * scale))
    sw    = max(1, int(stroke_width_px * scale))

    font_path = resolve_font(base_font_path) 
    font = ImageFont.truetype(font_path, fsize)
    # measure block
    widths, heights = [], []
    for line in text_lines:
        bbox = draw.textbbox((0,0), line, font=font, stroke_width=sw)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        widths.append(w); heights.append(h)
    block_w = max(widths) if widths else 0
    block_h = sum(heights) + gap * (len(text_lines) - 1 if text_lines else 0)

    cx, cy = center_xy
    x0 = int(cx - block_w/2)
    y0 = int(cy - block_h/2)

    y = y0
    for line, h in zip(text_lines, heights):
        draw.text((x0, y), line, font=font, fill=fill,
                  stroke_width=sw, stroke_fill=stroke_fill, align="center")
        y += h + gap


# --- Centered poster compositor with year-only dates ---


def compose_poster(
    series,
    image_paths,
    cols=6,
    size=(512, 768),              # (img_w, img_h) per tile
    margin=40,                    # outer margin
    gutter=24,                    # space between tiles
    base_font_path="assets/fonts/Inter-SemiBold.ttf",
    base_font_px=26,
    caption_scale=2.0,            # 2.0 = double-sized text
    line_gap_px=6,
    stroke_width_px=3,
    outpath=None,
    # --- new knobs ---
    max_long_side=None,           # e.g. 2048 or 4096
    max_megapixels=None,          # e.g. 6 (means ~6 MP)
    out_format="WEBP",            # "WEBP" | "JPEG" | "PNG"
    out_quality=80,               # WEBP/JPEG quality
):
    img_w, img_h = size
    n = len(image_paths)
    rows = ceil(n / cols)

    # caption height estimate
    line_h = int(base_font_px * caption_scale)
    caption_h = line_h * 2 + int(line_gap_px * caption_scale)

    canvas_w = margin*2 + cols*img_w + (cols-1)*gutter
    canvas_h = margin*2 + rows*(img_h + caption_h) + (rows-1)*gutter
    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")

    print(f"[compose] canvas {canvas_w} x {canvas_h} (~{canvas_w*canvas_h/1e6:.1f} MP)")

    def years_line(item):
        s = str(item.get("start") or "").strip()
        e = str(item.get("end") or "").strip()
        if not s and not e: return ""
        return f"{s} / {e or 'Present'}"

    k = 0
    for r in range(rows):
        for c in range(cols):
            if k >= n: break

            tile_x = margin + c * (img_w + gutter)
            tile_y = margin + r * (img_h + caption_h + gutter)

            im = Image.open(image_paths[k]).convert("RGB")
            if im.size != (img_w, img_h):
                im = im.resize((img_w, img_h), Image.Resampling.LANCZOS)
            canvas.paste(im, (tile_x, tile_y))

            # caption (centered)
            item = series["items"][k]
            name = item.get("name", "")
            yrs  = years_line(item)

            caption_center = (tile_x + img_w // 2, tile_y + img_h + caption_h // 2)
            draw_centered_multiline(
                canvas,
                [name, yrs],
                center_xy=caption_center,
                base_font_path=base_font_path,
                base_font_px=base_font_px,
                stroke_width_px=stroke_width_px,
                line_gap_px=line_gap_px,
                scale=caption_scale,
            )
            k += 1

    # --- downscale if requested ---
    W, H = canvas.size
    scale = 1.0
    if max_long_side:
        scale = min(scale, max_long_side / max(W, H))
    if max_megapixels:
        target_pixels = max_megapixels * 1_000_000
        scale = min(scale, sqrt(target_pixels / (W * H)))
    if scale < 1.0:
        new_size = (int(W * scale), int(H * scale))
        canvas = canvas.resize(new_size, Image.Resampling.LANCZOS)
        print(f"[compose] downscaled to {canvas.size} (~{canvas.size[0]*canvas.size[1]/1e6:.1f} MP)")

    # --- save compactly ---
    if outpath:
        if out_format.upper() == "WEBP":
            canvas.save(outpath, format="WEBP", quality=out_quality, method=6)  # method=6 = max effort
        elif out_format.upper() == "JPEG":
            canvas.save(outpath, format="JPEG", quality=out_quality, subsampling="4:2:0", optimize=True, progressive=True)
        elif out_format.upper() == "PNG":
            canvas.save(outpath, format="PNG", optimize=True, compress_level=9)
        else:
            canvas.save(outpath)  # fallback to extension-based
    return canvas


