from . import wikidata_series as wds
import geopandas as gpd, pandas as pd
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from io import BytesIO
import os, io, zipfile, requests, tempfile
import geopandas as gpd
from pathlib import Path

CACHE = Path("cache/natural_earth"); CACHE.mkdir(parents=True, exist_ok=True)

from PIL import ImageFont

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



NE_ADMIN0_URLS = [
    # primary S3 mirror
    "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip",
    # legacy mirror (sometimes works)
    "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
]
NE_ADMIN1_URLS = [
    "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_1_states_provinces.zip",
    "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip",
]

def _download_to_cache(urls, cache_fn):
    """Try each URL; cache the first that works."""
    if cache_fn.exists() and cache_fn.stat().st_size > 0:
        return cache_fn
    last_err = None
    for url in urls:
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            cache_fn.write_bytes(r.content)
            return cache_fn
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Failed to download Natural Earth: {last_err}")

def _read_ne_zip(cache_fn):
    # GeoPandas can read directly from a local .zip
    return gpd.read_file(f"zip://{cache_fn}")

def load_admin0():
    """Countries (admin-0). Falls back to GeoPandas lowres if mirrors fail."""
    zpath = CACHE / "ne_10m_admin_0_countries.zip"
    try:
        _download_to_cache(NE_ADMIN0_URLS, zpath)
        return _read_ne_zip(zpath)
    except Exception:
        # Fallback: built-in (lower resolution but good enough)
        return gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))

def load_admin1():
    """States/provinces (admin-1)."""
    zpath = CACHE / "ne_10m_admin_1_states_provinces.zip"
    _download_to_cache(NE_ADMIN1_URLS, zpath)
    return _read_ne_zip(zpath)


def filter_continent(gdf, continent="Europe"):
    return gdf[gdf["CONTINENT"]==continent]

def filter_admin1_by_country(gdf, country_name="United States"):
    return gdf[gdf["admin"].isin([country_name])]

# --- A1) Continent → countries (capital + ISO2) ---
# QIDs: Europe Q46, South America Q18, North America Q49, Asia Q48, Africa Q15, Oceania Q55643
def wd_countries_by_continent(continent_qid="Q46"):
    q = f"""
    SELECT ?country ?countryLabel ?iso2 ?capital ?capitalLabel ?coord WHERE {{
      ?country wdt:P31 wd:Q6256 .               # sovereign state
      ?country wdt:P30 wd:{continent_qid} .
      OPTIONAL {{ ?country wdt:P297 ?iso2. }}   # ISO2
      OPTIONAL {{
        ?country wdt:P36 ?capital .
        ?capital wdt:P625 ?coord .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    data = wds.wd_sparql(q)
    rows = []
    for b in data["results"]["bindings"]:
        if "coord" not in b: 
            continue
        lon, lat = map(float, b["coord"]["value"][6:-1].split())  # 'Point(lon lat)'
        rows.append({
            "level": "admin0",
            "country": b["countryLabel"]["value"],
            "iso2": b.get("iso2",{}).get("value"),
            "capital": b.get("capitalLabel",{}).get("value"),
            "lat": lat, "lon": lon
        })
    return pd.DataFrame(rows)

# --- A2) Country → first-level subdivisions (state/province) with capitals ---
# Examples: USA Q30, Canada Q16, Brazil Q155, Argentina Q414
def wd_admin1_capitals(country_qid="Q30"):
    q = f"""
    SELECT ?sub ?subLabel ?capital ?capitalLabel ?coord WHERE {{
      wd:{country_qid} wdt:P150 ?sub .          # contains admin divisions
      ?sub wdt:P36 ?capital .
      ?capital wdt:P625 ?coord .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    data = wds.wd_sparql(q)
    rows = []
    for b in data["results"]["bindings"]:
        lon, lat = map(float, b["coord"]["value"][6:-1].split())
        rows.append({
            "level": "admin1",
            "name": b["subLabel"]["value"],       # state/province name
            "capital": b["capitalLabel"]["value"],
            "lat": lat, "lon": lon
        })
    return pd.DataFrame(rows)


def wikidata_capitals_for_continent(continent_qid="Q46"):  # Q46=Europe, Q18=South America
    q = f"""
    SELECT ?country ?countryLabel ?iso2 ?capital ?capitalLabel ?coord WHERE {{
      ?country wdt:P30 wd:{continent_qid}.
      OPTIONAL {{ ?country wdt:P297 ?iso2. }}
      OPTIONAL {{
        ?country wdt:P36 ?capital .
        ?capital wdt:P625 ?coord .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    data = wds.wd_sparql(q)
    rows = []
    for b in data["results"]["bindings"]:
        if "coord" not in b:
            continue
        lon, lat = map(float, b["coord"]["value"][6:-1].split())  # 'Point(lon lat)'
        rows.append({
            "country": b["countryLabel"]["value"],
            "iso2": b.get("iso2",{}).get("value"),
            "capital": b.get("capitalLabel",{}).get("value"),
            "lat": lat, "lon": lon
        })
    return pd.DataFrame(rows)

CONTINENT_QID = {
    "europe": "Q46",
    "south america": "Q18",
    "north america": "Q49",
    "asia": "Q48",
    "africa": "Q15",
    "oceania": "Q55643",
}

COUNTRY_QID = {
    "united states": "Q30",
    "canada": "Q16",
    "brazil": "Q155",
    "argentina": "Q414",
}

def get_points_for_region(spec: str) -> tuple[gpd.GeoDataFrame, pd.DataFrame, str]:
    """
    Returns (base_polygons_gdf, points_df, label) for:
      - "Europe", "South America", etc.  -> admin0 polygons, country capital points + flags
      - "States in Continental US"       -> admin1 polygons (USA), state capitals (no flags)
      - "Provinces of Canada"            -> admin1 polygons (Canada), provincial capitals
      - "Map of South America"           -> same as 'South America'
    """
    s = spec.strip().lower()

    # Continents
    for cont in CONTINENT_QID:
        if cont in s:
            admin0 = load_admin0()
            base = filter_continent(admin0, continent=cont.title())
            pts = wd_countries_by_continent(CONTINENT_QID[cont])
            return base, pts, cont.title()

    # US States (contiguous)
    if "states" in s and ("united states" in s or "us" in s or "u.s." in s):
        admin1 = load_admin1()
        base = filter_admin1_by_country(admin1, "United States")
        # remove Alaska & Hawaii (optional)
        base = base[~base["name"].isin(["Alaska","Hawaii"])]
        pts = wd_admin1_capitals(COUNTRY_QID["united states"])
        return base, pts, "United States (Contiguous States)"

    # Canada Provinces
    if "provinces" in s and "canada" in s:
        admin1 = load_admin1()
        base = filter_admin1_by_country(admin1, "Canada")
        pts = wd_admin1_capitals(COUNTRY_QID["canada"])
        return base, pts, "Canada (Provinces & Territories)"

    # Fallback: try exact continent word
    if s in CONTINENT_QID:
        admin0 = load_admin0()
        base = filter_continent(admin0, continent=s.title())
        pts = wd_countries_by_continent(CONTINENT_QID[s])
        return base, pts, s.title()

    raise ValueError(f"Unsupported region spec: {spec!r}")


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


import os, requests
from PIL import ImageFont

FLAG_CACHE = Path("cache/flags"); FLAG_CACHE.mkdir(parents=True, exist_ok=True)

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
