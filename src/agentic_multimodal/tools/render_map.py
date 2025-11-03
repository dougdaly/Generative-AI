from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import os
import geopandas as gpd
from io import BytesIO
import requests

FLAG_CACHE = Path("cache/flags"); FLAG_CACHE.mkdir(parents=True, exist_ok=True)


def resolve_font(preferred: str | None = None):
    """
    Return a path or font name that ImageFont.truetype can open.
    Tries: user-supplied path → common system fonts → Pillow's bundled DejaVu.
    """
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


def flag_image_for_iso2(iso2: str, size=64):
    if not iso2:
        return None
    fn = FLAG_CACHE / f"{iso2.lower()}_{size}.png"
    if fn.exists():
        return Image.open(fn).convert("RGBA")
    url = f"https://flagcdn.com/w{size}/{iso2.lower()}.png"
    r = requests.get(url, timeout=20)
    if r.status_code != 200:  # some territories lack a flag at this CDN
        return None
    img = Image.open(BytesIO(r.content)).convert("RGBA")
    img.save(fn)
    return img


def render_region_map(base_gdf, points_df, outpath="out/region_map.png", epsg=3857, title: str | None = None):
    g = base_gdf.to_crs(epsg=epsg)
    ax = g.plot(edgecolor="#333", linewidth=0.5, facecolor="#f5f6fa", figsize=(14,10))
    fig = ax.get_figure()
    Path("out").mkdir(exist_ok=True, parents=True)
    tmp = "out/_base.png"
    fig.savefig(tmp, dpi=300, bbox_inches="tight")
    fig.clf()

    base = Image.open(tmp).convert("RGBA")
    draw = ImageDraw.Draw(base)
    font_path = resolve_font(None)
    font = ImageFont.truetype(font_path, 18)

    minx, miny, maxx, maxy = g.total_bounds
    W, H = base.size
    def to_px(xy):
        x = int((xy[0] - minx) / (maxx - minx) * W)
        y = int(H - (xy[1] - miny) / (maxy - miny) * H)
        return x, y

    pts = gpd.GeoDataFrame(points_df, geometry=gpd.points_from_xy(points_df["lon"], points_df["lat"]), crs=4326).to_crs(epsg=epsg)

    for _, row in pts.iterrows():
        x, y = to_px((row.geometry.x, row.geometry.y))
        label = f"{row.get('country') or row.get('name')} ({row.get('capital','')})".strip()

        # Country level → draw flag; Admin1 → draw dot
        if row.get("level") == "admin0" and isinstance(row.get("iso2"), str) and len(row["iso2"]) == 2:
            flag = flag_image_for_iso2(row["iso2"], size=48)
            if flag:
                base.alpha_composite(flag, dest=(x-flag.width//2, y-flag.height//2))
                x_text = x + flag.width//2 + 6
                y_text = y - 10
            else:
                # fallback to dot
                r = 5
                draw.ellipse((x-r,y-r,x+r,y+r), fill="#d22", outline="#111")
                x_text = x + 10; y_text = y - 8
        else:
            r = 5
            draw.ellipse((x-r,y-r,x+r,y+r), fill="#0a6", outline="#111")
            x_text = x + 10; y_text = y - 8

        # Text with light halo for contrast
        draw.text((x_text+1, y_text+1), label, fill="white", font=font)
        draw.text((x_text, y_text), label, fill="black", font=font)

    # Title
    if title:
        big = ImageFont.truetype(font_path, 28)
        tw, th = draw.textbbox((0,0), title, font=big)[2:]
        draw.text(((W-tw)//2+2, 8+2), title, fill="white", font=big)
        draw.text(((W-tw)//2, 8), title, fill="black", font=big)

    base.convert("RGB").save(outpath, optimize=True)
    return outpath


NE_URL = "https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/cultural/ne_10m_admin_0_countries.zip"

def _download_flag(iso2:str, size=64):
    # Flagpedia PNG by ISO2 (lowercase): https://flagcdn.com/w80/{code}.png also works
    url = f"https://flagcdn.com/w{size}/{iso2.lower()}.png"
    r = requests.get(url, timeout=20)
    return Image.open(BytesIO(r.content)).convert("RGBA")

def render_europe_map(capitals_df: pd.DataFrame):
    world = gpd.read_file(NE_URL)  # GeoDataFrame with polygons for countries
    europe = world[world["CONTINENT"]=="Europe"]  # quick filter; refine if needed
    # Project to something Europe-friendly (EPSG: 3035 or 3857); use 3857 for simplicity
    europe = europe.to_crs(epsg=3857)

    # Build base canvas via Matplotlib to an image
    ax = europe.plot(edgecolor="black", linewidth=0.5, facecolor="#f5f6fa", figsize=(12,9))
    fig = ax.get_figure()
    fig.savefig("out/_europe_base.png", dpi=300, bbox_inches="tight")
    fig.clf()

    base = Image.open("out/_europe_base.png").convert("RGBA")
    draw = ImageDraw.Draw(base)
    font = ImageFont.load_default()

    # Convert lat/lon to projected coordinates, then image pixels
    capitals_gdf = gpd.GeoDataFrame(
        capitals_df,
        geometry=gpd.points_from_xy(capitals_df["lon"], capitals_df["lat"]),
        crs=4326
    ).to_crs(europe.crs)

    # crude pixel mapping: use bbox of the saved figure
    # For more precise placement, render directly with matplotlib scatter + image annotations.

    minx, miny, maxx, maxy = europe.total_bounds
    W, H = base.size

    def to_px(pt):
        x = int((pt.x - minx) / (maxx - minx) * W)
        y = int(H - (pt.y - miny) / (maxy - miny) * H)
        return x, y

    for _, row in capitals_gdf.iterrows():
        try:
            flag = _download_flag(row["iso2"], size=64)
        except Exception:
            continue
        x, y = to_px(row.geometry)
        base.alpha_composite(flag, dest=(x-flag.width//2, y-flag.height//2))
        draw.text((x+36, y-8), f'{row["country"]} ({row["capital"]})', fill="black", font=font)

    os.makedirs("out", exist_ok=True)
    out_path = "out/europe_map.png"
    base.convert("RGB").save(out_path, optimize=True)
    return out_path
