from typing import List, Dict, Optional
from agentic_multimodal.schemas.entities import Person, OfficeTerm
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import SeriesProvider

class PerCountrySelector(SeriesProvider):
    """
    Generic: pick top entity per country using a CandidateProvider + Ranker.
    You register concrete keys in the registry by partially applying provider/ranker.
    """
    def __init__(self, key: str, title: str, provider, ranker):
        self.key, self.title = key, title
        self._provider, self._ranker = provider, ranker

    def fetch(
        self,
        client: WikidataSPARQL,
        *,
        language: str = "en",
        country_qid: str,
        limit_candidates: int = 20,
        pageviews_days: int = 60,
        http_timeout: int = 8,
        sleep_between: float = 0.2,
        retries: int = 2,
        fallback: Optional[str] = "leader",
        **kwargs,  # forward-compat
    ) -> List[Person]:
        cands = self._provider.candidates(client, country_qid=country_qid, language=language)
        if not cands: return []
        scored = [(self._ranker.score(c["qid"], c["label"]), c) for c in cands]
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        # We return a Person; terms empty (map label only) — you can add metadata later
        return [Person(qid=best["qid"], name=best["label"], image_url=best.get("image"), terms=[])]
