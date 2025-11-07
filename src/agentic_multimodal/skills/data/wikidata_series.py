# keep your existing header imports
from typing import Dict, List, Optional, Protocol, runtime_checkable
from agentic_multimodal.schemas.entities import Person, OfficeTerm
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL

def _to_iso_or_none(x: Optional[str]) -> Optional[str]:
    if not x:
        return None
    x = x.lstrip("+")
    if len(x) >= 10 and x[4] == "-" and x[7] == "-":
        return x[:10]          # YYYY-MM-DD
    if len(x) >= 4 and x[:4].isdigit():
        return f"{x[:4]}-01-01"
    return None

@runtime_checkable
class SeriesProvider(Protocol):
    key: str
    title: str
    # Providers can declare any **params they need (award_qid, position_qids, etc.)
    def fetch(self, client: WikidataSPARQL, *, language: str = "en", **params) -> List[Person]: ...

class WikidataSeries:
    def __init__(self, sparql_client: WikidataSPARQL, *, language: str = "en"):
        self.sparql = sparql_client
        self.language = language
        self._providers: Dict[str, SeriesProvider] = {}

    def register(self, provider: SeriesProvider) -> None:
        self._providers[provider.key] = provider

    def available(self) -> List[str]:
        return sorted(self._providers.keys())

    def run(self, key: str, **overrides):
        prov = self._providers[key]
        params = {**getattr(prov, "_fixed", {}), **overrides}
        params.setdefault("language", self.language)  # ensure it’s there
        base = getattr(prov, "base", prov)            # unwrap alias
        return base.fetch(self.sparql, **params)      # pass once
