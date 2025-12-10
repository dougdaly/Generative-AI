from __future__ import annotations
# This provides functions and parameters related to collecting information about a geographic region, the bounding polygon(s) for map creation, the capital, and flag.

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, runtime_checkable, Iterable
from agentic_multimodal.schemas.entities import Country
from agentic_multimodal.skills.data.wikidata_search_label import search_labels


from .wikidata_sparql import WikidataSPARQL

PREFIXES = """
PREFIX wd:   <http://www.wikidata.org/entity/>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX bd:   <http://www.bigdata.com/rdf#>
PREFIX geo:  <http://www.opengis.net/ont/geosparql#>
PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
"""

def _as_items(qids: Iterable[str]) -> str:
    """Render VALUES list like: wd:Q30 wd:Q90 …"""
    return " ".join(f"wd:{qid.lstrip('wd:')}" for qid in qids)

from typing import Optional, Tuple
from agentic_multimodal.skills.data.wikidata_search_label import _get

def coords_for_qid(qid: str) -> Optional[Tuple[float, float]]:
    """
    Returns (lat, lon) from Wikidata P625, or None.
    Uses the same _get transport as search_labels.
    """
    if not qid or not qid.startswith("Q"):
        return None

    data = _get({
        "action": "wbgetentities",
        "format": "json",
        "ids": qid,
        "props": "claims",
    })

    ent = data.get("entities", {}).get(qid, {})
    claims = ent.get("claims", {})
    p625 = claims.get("P625")
    if not p625:
        return None

    mainsnak = p625[0].get("mainsnak", {})
    datavalue = mainsnak.get("datavalue", {})
    value = datavalue.get("value", {})

    lat = value.get("latitude")
    lon = value.get("longitude")
    if lat is None or lon is None:
        return None

    return (float(lat), float(lon))


@dataclass
class WikidataGeo:
    """Tiny helper around Wikidata SPARQL for coordinates & labels."""
    sparql: WikidataSPARQL

    @classmethod
    def default(cls) -> "WikidataGeo":
        return cls(sparql=WikidataSPARQL())

    def coords_for(self, qids: Iterable[str]) -> List[Dict]:
        """
        Return lat/lon + basic labels for the given QIDs.
        Output rows: { 'qid', 'label', 'lat', 'lon', 'country', 'countryLabel' (optional) }
        """
        items = _as_items(qids)
        query = f"""
        {PREFIXES}
        SELECT ?item ?itemLabel ?coord ?lat ?lon ?country ?countryLabel WHERE {{
          VALUES ?item {{ {items} }}
          ?item wdt:P625 ?coord .
          OPTIONAL {{ ?item wdt:P17 ?country . }}
          BIND(geof:latitude(?coord)  AS ?lat)
          BIND(geof:longitude(?coord) AS ?lon)
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        """
        rows = self.sparql.run(query)
        out: List[Dict] = []
        for r in rows:
            out.append({
                "qid": r.get("item", {}).get("value", "").rpartition("/")[-1],
                "label": r.get("itemLabel", {}).get("value"),
                "lat": float(r["lat"]["value"]) if "lat" in r else None,
                "lon": float(r["lon"]["value"]) if "lon" in r else None,
                "country_qid": r.get("country", {}).get("value", "").rpartition("/")[-1] or None,
                "countryLabel": r.get("countryLabel", {}).get("value"),
            })
        return out

    def bbox_places(
        self,
        west: float,
        south: float,
        east: float,
        north: float,
        limit: int = 200,
        instance_of_qids: Optional[Iterable[str]] = None,
    ) -> List[Dict]:
        """
        Find items with coordinates inside a lat/lon bounding box.
        Optionally filter by instance-of (P31) types.
        """
        inst_values = (
            " ".join(f"wd:{qid.lstrip('wd:')}" for qid in instance_of_qids)
            if instance_of_qids else ""
        )
        inst_filter = f"VALUES ?type {{ {inst_values} }} . ?item wdt:P31 ?type ." if inst_values else ""
        # Wikidata stores P625 as WKT POINT(lon lat)
        query = f"""
        {PREFIXES}
        SELECT ?item ?itemLabel ?coord ?lat ?lon WHERE {{
          ?item wdt:P625 ?coord .
          {inst_filter}
          BIND(geof:latitude(?coord)  AS ?lat)
          BIND(geof:longitude(?coord) AS ?lon)
          FILTER(?lat >= {south} && ?lat <= {north} && ?lon >= {west} && ?lon <= {east})
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT {int(limit)}
        """
        rows = self.sparql.run(query)
        out: List[Dict] = []
        for r in rows:
            out.append({
                "qid": r.get("item", {}).get("value", "").rpartition("/")[-1],
                "label": r.get("itemLabel", {}).get("value"),
                "lat": float(r["lat"]["value"]) if "lat" in r else None,
                "lon": float(r["lon"]["value"]) if "lon" in r else None,
            })
        return out

# --- Geo dispatcher & provider protocol ---

@runtime_checkable
class GeoProvider(Protocol):
    key: str
    title: str
    def fetch(self, geo: "WikidataGeo", *, language: str = "en", **params) -> List[Country]: ...

class WikidataGeoSets:
    """Thin dispatcher that hosts named geo sets built from WikidataGeo."""
    def __init__(self, geo_client: "WikidataGeo", *, language: str = "e n"):
        self.geo = geo_client
        self.client = geo_client
        self.language = language
        self._providers: Dict[str, GeoProvider] = {}

    def register(self, provider: GeoProvider) -> None:
        self._providers[provider.key] = provider

    def available(self) -> List[str]:
        return sorted(self._providers.keys())

    def run(self, key: str, **params) -> List[Country]:
        if key not in self._providers:
            raise KeyError(f"Unknown geo set '{key}'. Have: {self.available()}")
        return self._providers[key].fetch(self.geo, language=self.language, **params)

_BAD_DESC_TOKENS = (
    "people from", "residents of", "demonym",
    "episode of", "pandemic", "covid",
    "auditions", "film", "song", "album",
)

_GOOD_DESC_TOKENS = (
    "city", "capital", "town", "municip",
    "human settlement", "metropolis",
    "province", "state", "country",
)

def _candidate_queries(label: str):
    s = (label or "").strip()
    if not s:
        return []

    out = [s]

    # If "City, Country", try "City" and "City Country"
    if "," in s:
        left = s.split(",", 1)[0].strip()
        right = s.split(",", 1)[1].strip()
        if left:
            out.append(left)
        if left and right:
            out.append(f"{left} {right}")

    # Also try removing parentheses or extra punctuation
    out.append(s.replace(",", " "))
    out.append(" ".join(s.split()))

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for q in out:
        qn = q.lower()
        if qn not in seen:
            seen.add(qn)
            deduped.append(q)
    return deduped

def geocode_place(self, label: str):
    lang = getattr(self, "language", "en")

    last_top = None

    for q in _candidate_queries(label):
        hits = search_labels(q, language=lang, limit=20)

        if not hits:
            continue

        # Bucket hits by description quality
        good = []
        meh = []
        bad = []

        for h in hits:
            desc = (getattr(h, "description", "") or "").lower()

            if any(t in desc for t in _BAD_DESC_TOKENS):
                bad.append(h)
            elif any(t in desc for t in _GOOD_DESC_TOKENS):
                good.append(h)
            else:
                meh.append(h)

        ordered = good + meh + bad

        for h in ordered:
            coords = coords_for_qid(h.qid)
            if coords:
                return coords

        last_top = [(h.qid, getattr(h, "label", ""), getattr(h, "description", "")) for h in hits[:5]]

    raise ValueError(f"No coordinates found for '{label}'. Top hits: {last_top or []}")



__all__ = ["WikidataGeo", "WikidataGeoSets"]

