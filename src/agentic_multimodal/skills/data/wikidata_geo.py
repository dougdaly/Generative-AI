from __future__ import annotations
# This provides functions and parameters related to collecting information about a geographic region, the bounding polygon(s) for map creation, the capital, and flag.

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, runtime_checkable, Iterable
from agentic_multimodal.schemas.entities import Country


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
    def fetch(self, client: "WikidataGeo", *, language: str = "en", **params) -> List[Country]: ...

class WikidataGeoSets:
    """Thin dispatcher that hosts named geo sets built from WikidataGeo."""
    def __init__(self, geo_client: "WikidataGeo", *, language: str = "e n"):
        self.geo = geo_client
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


__all__ = ["WikidataGeo", "WikidataGeoSets"]

