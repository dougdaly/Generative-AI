from . import wikidata_series as wds
import geopandas as gpd, pandas as pd
from pathlib import Path
from io import BytesIO
import os, requests
import geopandas as gpd
from pathlib import Path
from PIL import ImageFont

# This provides functions and parameters related to collecting information about a geographic region, the bounding polygon(s) for map creation, the capital, and flag.

CACHE = Path("cache/natural_earth"); CACHE.mkdir(parents=True, exist_ok=True)

SOURCES = {'NE_ADMIN0': 
           {
                'URLs': [
                    # primary S3 mirror
                    "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip",
                    # legacy mirror (sometimes works)
                    "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
                    ],
                'Cache': "ne_10m_admin_0_countries.zip"
            },
    'NE_ADMIN1' : 
        {
            'URLs': [
                "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_1_states_provinces.zip",
                "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip",
                ],
            'Cache': "ne_10m_admin_1_states_provinces.zip" 
        }
    }


# Download map data to cache
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

def load_admin(admin_key: str):
    """ Countries (admin_0), states/provinces (admin_1)"""
    zpath = CACHE / SOURCES[admin_key]['Cache']
    _download_to_cache(SOURCES[admin_key]['URLs'], zpath)
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
            admin0 = load_admin('NE_ADMIN0')
            base = filter_continent(admin0, continent=cont.title())
            pts = wd_countries_by_continent(CONTINENT_QID[cont])
            return base, pts, cont.title()

    # US States (contiguous)
    if "states" in s and ("united states" in s or "us" in s or "u.s." in s):
        admin1 = load_admin('NE_ADMIN1')
        base = filter_admin1_by_country(admin1, "United States")
        # remove Alaska & Hawaii (optional)
        base = base[~base["name"].isin(["Alaska","Hawaii"])]
        pts = wd_admin1_capitals(COUNTRY_QID["united states"])
        return base, pts, "United States (Contiguous States)"

    # Canada Provinces
    if "provinces" in s and "canada" in s:
        admin1 = load_admin('NE_ADMIN1')
        base = filter_admin1_by_country(admin1, "Canada")
        pts = wd_admin1_capitals(COUNTRY_QID["canada"])
        return base, pts, "Canada (Provinces & Territories)"

    # Fallback: try exact continent word
    if s in CONTINENT_QID:
        admin0 = load_admin('NE_ADMIN0')
        base = filter_continent(admin0, continent=s.title())
        pts = wd_countries_by_continent(CONTINENT_QID[s])
        return base, pts, s.title()

    raise ValueError(f"Unsupported region spec: {spec!r}")


