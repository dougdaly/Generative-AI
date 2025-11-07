from typing import List
from agentic_multimodal.schemas.entities import Person
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_geo import GeoProvider

class PreconfiguredProvider(GeoProvider):
    def __init__(self, key: str, title: str, base: GeoProvider, **fixed_params):
        self.key = key
        self.title = title
        self._base = base
        self._fixed = fixed_params

    def fetch(self, client: WikidataSPARQL, *, language: str = "en", **params) -> List[Person]:
        merged = {**self._fixed, **params}
        return self._base.fetch(client, language=language, **merged)