# src/agentic_multimodal/skills/map_regions.py
# orchestrator engine
from __future__ import annotations
import pandas as pd
import geopandas as gpd
from typing import Tuple

from .natural_earth import load_admin, filter_continent, filter_admin1_by_country
from data.wikidata_geo import WikidataGeo

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

def _countries_capitals_df(geo: WikidataGeo, continent_qid: str) -> pd.DataFrame:
    # country + capital coords via Wikidata
    qids = []  # optional: if you want specific countries, else query by continent
    # Simpler: one SPARQL query that pulls countries-in-continent + capital coords:
    # reuse the query from your earlier code, but run it through geo.sparql.run(...)
    query = f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX bd: <http://www.bigdata.com/rdf#>
    PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
    SELECT ?country ?countryLabel ?iso2 ?capital ?capitalLabel ?coord ?lat ?lon WHERE {{
      ?country wdt:P31 wd:Q6256 ;
               wdt:P30 wd:{continent_qid} .
      OPTIONAL {{ ?country wdt:P297 ?iso2. }}
      OPTIONAL {{
        ?country wdt:P36 ?capital .
        ?capital wdt:P625 ?coord .
        BIND(geof:latitude(?coord)  AS ?lat)
        BIND(geof:longitude(?coord) AS ?lon)
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    rows = geo.sparql.run(query)
    out = []
    for r in rows:
        if "lat" not in r or "lon" not in r:
            continue
        out.append({
            "level": "admin0",
            "country": r.get("countryLabel",{}).get("value"),
            "iso2":    r.get("iso2",{}).get("value"),
            "capital": r.get("capitalLabel",{}).get("value"),
            "lat": float(r["lat"]["value"]),
            "lon": float(r["lon"]["value"]),
        })
    return pd.DataFrame(out)

def _admin1_capitals_df(geo: WikidataGeo, country_qid: str) -> pd.DataFrame:
    query = f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX bd: <http://www.bigdata.com/rdf#>
    PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
    SELECT ?sub ?subLabel ?capital ?capitalLabel ?coord ?lat ?lon WHERE {{
      wd:{country_qid} wdt:P150 ?sub .
      ?sub wdt:P36 ?capital .
      ?capital wdt:P625 ?coord .
      BIND(geof:latitude(?coord)  AS ?lat)
      BIND(geof:longitude(?coord) AS ?lon)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    rows = geo.sparql.run(query)
    out = []
    for r in rows:
        out.append({
            "level": "admin1",
            "name":    r.get("subLabel",{}).get("value"),
            "capital": r.get("capitalLabel",{}).get("value"),
            "lat": float(r["lat"]["value"]),
            "lon": float(r["lon"]["value"]),
        })
    return pd.DataFrame(out)

def get_points_for_region(spec: str, geo: WikidataGeo) -> Tuple[gpd.GeoDataFrame, pd.DataFrame, str]:
    s = spec.strip().lower()

    # Continents
    for cont, qid in CONTINENT_QID.items():
        if cont in s or s == cont:
            admin0 = load_admin("NE_ADMIN0")
            base = filter_continent(admin0, continent=cont.title())
            pts = _countries_capitals_df(geo, qid)
            return base, pts, cont.title()

    # US States (contiguous)
    if "states" in s and ("united states" in s or "us" in s or "u.s." in s):
        admin1 = load_admin("NE_ADMIN1")
        base = filter_admin1_by_country(admin1, "United States")
        base = base[~base["name"].isin(["Alaska", "Hawaii"])]
        pts = _admin1_capitals_df(geo, COUNTRY_QID["united states"])
        return base, pts, "United States (Contiguous States)"

    # Canada Provinces
    if "provinces" in s and "canada" in s:
        admin1 = load_admin("NE_ADMIN1")
        base = filter_admin1_by_country(admin1, "Canada")
        pts = _admin1_capitals_df(geo, COUNTRY_QID["canada"])
        return base, pts, "Canada (Provinces & Territories)"

    raise ValueError(f"Unsupported region spec: {spec!r}")
