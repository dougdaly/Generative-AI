#Provides subdivisions of a country (US states, Canadian provinces, etc.)
from typing import Dict, List, Optional, Iterable
from agentic_multimodal.schemas.entities import Country
from agentic_multimodal.skills.data.wikidata_geo import WikidataGeo, GeoProvider

def _v(b: Dict, k: str) -> Optional[str]:
    v = b.get(k);  return v.get("value") if isinstance(v, dict) else None

def _ensure_qid(x: str) -> str:
    return x.rsplit("/", 1)[-1]

def _values_q(qids: Iterable[str]) -> str:
    return " ".join(f"wd:{_ensure_qid(q)}" for q in qids)

class SubdivisionsByCountryProvider(GeoProvider):
    key   = "subdivisions"
    title = "Country subdivisions with flags and capital coords"

    def fetch(
        self,
        client: WikidataGeo,
        *,
        language: str = "en",
        country_qid: str,
        instance_of_qids: List[str],
    ) -> List[Country]:

        country = _ensure_qid(country_qid)
        inst_values = _values_q(instance_of_qids)

        q = f"""
        SELECT ?s ?sLabel ?flag ?capLabel ?coord WHERE {{
          VALUES ?type {{ {inst_values} }}
          ?s wdt:P31 ?type .
          ?s wdt:P17 wd:{country} .
          OPTIONAL {{ ?s wdt:P41 ?flag . }}
          OPTIONAL {{ ?s wdt:P36 ?cap . ?cap rdfs:label ?capLabel .
                     FILTER(LANG(?capLabel)="{language}") . ?cap wdt:P625 ?coord . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}" . }}
        }}
        ORDER BY ?sLabel
        """
        rows = client.sparql.run(q)
        out: List[Country] = []
        for r in rows:
            uri = _v(r, "s")
            if not uri: continue
            qid  = _ensure_qid(uri)
            name = _v(r, "sLabel") or qid
            flag = _v(r, "flag")
            cap  = _v(r, "capLabel")
            wkt  = _v(r, "coord")
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
