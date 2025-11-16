from typing import Protocol, List
from agentic_multimodal.schemas.entities import Country
from agentic_multimodal.skills.data.wikidata_geo import WikidataGeo

class GeoProvider(Protocol):
    key: str
    title: str
    def fetch(self, client: WikidataGeo, *, language: str = "en", **params) -> List[Country]:
        ...

__all__ = ["GeoProvider"]