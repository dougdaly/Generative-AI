# skills/series/aliases.py

from typing import List, Dict, Any
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.schemas.entities import Person

class PreconfiguredProvider:
    """
    Wraps a base provider with fixed params. Also normalizes language handling.
    """
    def __init__(self, key: str, title: str, base, **fixed):
        self.key = key
        self.title = title
        self.base = base          # use a consistent attr name
        self._fixed = fixed

    def fetch(self, client: WikidataSPARQL, **params) -> List[Person]:
        # Merge fixed + overrides
        merged: Dict[str, Any] = {**self._fixed, **params}
        # Normalize language (prefer explicit param, else series default, else chain)
        language = merged.pop("language", "[AUTO_LANGUAGE],en")
        # Pass language exactly once
        return self.base.fetch(client, language=language, **merged)
