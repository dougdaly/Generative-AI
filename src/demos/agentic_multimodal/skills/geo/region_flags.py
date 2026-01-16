# skills/geo/region_flags.py
from typing import Dict, List, Optional, Iterable
from dataclasses import dataclass
from agentic_multimodal.schemas.entities import Country
from agentic_multimodal.skills.data.wikidata_geo import WikidataGeo
from agentic_multimodal.skills.geo.__init__ import GeoProvider  # your existing base

# Defaults:
QID_COUNTRY = "Q6256"   # sovereign state
# Examples for region_qids: Europe Q46, Asia Q48, Africa Q15, North America Q49, South America Q18, Oceania Q55643

def _v(b: Dict, k: str) -> Optional[str]:
    v = b.get(k);  return v.get("value") if isinstance(v, dict) else None

@dataclass
class RegionCountriesWithFlags(GeoProvider):
    """
    Generic: countries in given continent/region(s), with flag + capital coords.
    Params are passed at call-time or via a preconfigured alias.
    """
    key: str = "region_countries_flags"
    title: str = "Region: countries, flags, capital coords"

    def fetch(
        self,
        client: WikidataGeo,
        *,
        language: str = "en",
        region_qids: Iterable[str],                    # e.g. ["Q46"] for Europe
        instance_of_qids: Iterable[str] = (QID_COUNTRY,),  # override for provinces/territories if needed
        min_pop: Optional[int] = None,                 # optional microstate filter
        min_area_km2: Optional[float] = None,          # optional microstate filter
    ) -> List[Country]:
        regions = " ".join(f"wd:{str(q).lstrip('wd:')}" for q in region_qids)
        insts   = " ".join(f"wd:{str(q).lstrip('wd:')}" for q in instance_of_qids)

        pop_filter  = f"FILTER(?pop >= {int(min_pop)})" if min_pop else ""
        area_filter = f"FILTER(?area >= {float(min_area_km2)})" if min_area_km2 else ""
        q = f"""
            PREFIX wd:       <http://www.wikidata.org/entity/>
            PREFIX wdt:      <http://www.wikidata.org/prop/direct/>
            PREFIX p:        <http://www.wikidata.org/prop/>
            PREFIX psv:      <http://www.wikidata.org/prop/statement/value/>
            PREFIX wikibase: <http://wikiba.se/ontology#>
            PREFIX rdfs:     <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX schema:   <http://schema.org/>

            SELECT
                ?c ?cLabel
                (SAMPLE(?flag)     AS ?flag)
                (SAMPLE(?capLabel) AS ?capLabel)
                (SAMPLE(?lat)      AS ?lat)
                (SAMPLE(?lon)      AS ?lon)
                (SAMPLE(?pop)      AS ?pop)
                (SAMPLE(?area)     AS ?area) 
            WHERE {{
            VALUES ?region {{ {regions} }}
            VALUES ?klass  {{ {insts}  }}

            ?c wdt:P31 ?klass .
            ?c wdt:P30 ?region .

            OPTIONAL {{ ?c wdt:P41 ?flag . }}

            OPTIONAL {{
                ?c wdt:P36 ?cap .
                ?cap p:P625/psv:P625 ?capCoordVal .
                ?capCoordVal wikibase:geoLatitude  ?lat ;
                            wikibase:geoLongitude ?lon .
                OPTIONAL {{
                ?cap rdfs:label ?capLabelRaw .
                FILTER(LANGMATCHES(LANG(?capLabelRaw), "en"))
                }}
                OPTIONAL {{
                ?cap schema:name ?capLabel2 .
                FILTER(LANGMATCHES(LANG(?capLabel2), "en"))
                }}
                BIND(COALESCE(?capLabelRaw, ?capLabel2) AS ?capLabel)
            }}

            OPTIONAL {{ ?c wdt:P1082 ?pop . }}   # population
            OPTIONAL {{ ?c wdt:P2046 ?area . }}  # area m²

            {pop_filter}
            {area_filter}

            SERVICE wikibase:label {{
                bd:serviceParam wikibase:language "en,[AUTO_LANGUAGE]" .
                }}
            }}
            GROUP BY ?c ?cLabel
            ORDER BY ?cLabel
            """

        rows = client.sparql.run(q)
        out: List[Country] = []
        for r in rows:
            uri = _v(r, "c")
            if not uri: 
                continue
            qid  = uri.rsplit("/", 1)[-1]
            name = _v(r, "cLabel") or qid
            flag = _v(r, "flag")
            cap  = _v(r, "capLabel")

            lat_s = r.get("lat", {}).get("value")
            lon_s = r.get("lon", {}).get("value")
            coords = (float(lon_s), float(lat_s)) if (lat_s and lon_s) else None

            pop_s  = _v(r, "pop")
            area_s = _v(r, "area")

            population = int(float(pop_s)) if pop_s else None
            area_km2   = float(area_s)/1_000_000.0 if area_s else None

            out.append(Country(
                qid=qid,
                name=name,
                capital_name=cap,
                capital_coords=coords,          # ← use numeric tuple
                flag_svg_url=flag,
                population=population,          # ← now populated
                area_km2=area_km2,
            ))
        return out
