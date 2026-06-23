# Deprecated file: europe_flags.py

from typing import Dict, List, Optional
from agentic_multimodal.schemas.entities import Country
from agentic_multimodal.skills.data.wikidata_geo import WikidataGeo, GeoProvider

QID_EUROPE  = "Q46"    # continent
QID_COUNTRY = "Q6256"  # sovereign state

def _v(b: Dict, k: str) -> Optional[str]:
    v = b.get(k);  return v.get("value") if isinstance(v, dict) else None

class EuropeCountriesWithFlags(GeoProvider):
    key   = "europe_countries_flags"
    title = "Europe: countries, flags, capital coords"

    def fetch(self, client: WikidataGeo, *, language: str = "en") -> List[Country]:
        q = f"""
        SELECT ?c ?cLabel ?flag ?capLabel ?coord WHERE {{
          ?c wdt:P31 wd:{QID_COUNTRY} .
          ?c wdt:P30 wd:{QID_EUROPE} .
          OPTIONAL {{ ?c wdt:P41 ?flag . }}                                   # flag (SVG ok)
          OPTIONAL {{ ?c wdt:P36 ?cap . ?cap rdfs:label ?capLabel .
                     FILTER(LANG(?capLabel)="{language}") . ?cap wdt:P625 ?coord . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}" . }}
        }}
        ORDER BY ?cLabel
        """
        rows = client.sparql.run(q)
        out: List[Country] = []
        for r in rows:
            uri = _v(r, "c")
            if not uri: continue
            qid  = uri.rsplit("/", 1)[-1]
            name = _v(r, "cLabel") or qid
            flag = _v(r, "flag")
            cap  = _v(r, "capLabel")
            wkt  = _v(r, "coord")      # "Point(lon lat)"
            lon = lat = None
            if wkt and "Point(" in wkt:
                try:
                    inner = wkt.split("Point(",1)[1].split(")",1)[0].strip()
                    lon_s, lat_s = inner.split()
                    lon, lat = float(lon_s), float(lat_s)
                except Exception:
                    pass
            out.append(Country(
                qid=qid,
                name=name,
                capital_name=cap,
                capital_coords=(lon, lat) if lon is not None and lat is not None else None,
                flag_svg_url=flag,
            ))
        return out
