from PIL import Image, ImageDraw, ImageFont
from schemas import PresidentList
import math, os

def compose_node(state):
    plist = PresidentList(**state["research"])
    imgs = [state["images"][str(i+1)] for i in range(len(plist.people))]
    tiles_w, tiles_h = 6, math.ceil(len(imgs)/6)
    tile_w, tile_h = 512, 860  # include caption band
    margin, pad = 40, 20
    W = margin*2 + tiles_w*tile_w + (tiles_w-1)*pad
    H = margin*2 + tiles_h*tile_h + (tiles_h-1)*pad
    poster = Image.new("RGB", (W,H), "white")
    draw = ImageDraw.Draw(poster)
    font = ImageFont.load_default()

    for idx, path in enumerate(imgs):
        r, c = divmod(idx, tiles_w)
        x = margin + c*(tile_w+pad)
        y = margin + r*(tile_h+pad)
        im = Image.open(path).convert("RGB").resize((512,768))
        poster.paste(im, (x, y))
        person = plist.people[idx]
        caption = f"{person.name}\n{person.start} – {person.end}"
        draw.multiline_text((x+10, y+768+10), caption, fill="black", font=font, spacing=2)

    os.makedirs("out", exist_ok=True)
    out_path = "out/presidents_poster.png"
    poster.save(out_path, optimize=True)
    return {**state, "artifact": out_path}

# src/agents/compositor.py (add a map function)
import geopandas as gpd, pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os

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
