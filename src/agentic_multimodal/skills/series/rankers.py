# Simple, swappable rankers

from typing import Protocol, Tuple, Optional
from agentic_multimodal.skills.data.wiki_pageviews import last_n_days_pageviews

class Ranker(Protocol):
    def score(self, qid: str, label: str) -> float: ...

class PageviewsRanker:
    def __init__(self, days: int = 60): self.days = days
    def score(self, qid: str, label: str) -> float:
        try: return float(last_n_days_pageviews(label, days=self.days))
        except Exception: return 0.0

class SitelinksRanker:
    # quick, offline-ish proxy using sitelinks count
    def __init__(self, client): self.client = client  # WikidataSPARQL
    def score(self, qid: str, label: str) -> float:
        q = f"SELECT (COUNT(?link) AS ?n) WHERE {{ wd:{qid} ?p ?link . FILTER(STRSTARTS(STR(?p),'http://www.wikidata.org/prop/direct/sitelinks/')) }}"
        rows = self.client.run(q)
        try: return float(rows[0]["n"]["value"])
        except Exception: return 0.0

class OverridesRanker:
    # boost or pin manual picks, e.g., {"Q29":"Rafael Nadal"}
    def __init__(self, overrides: dict[str,str], base: Ranker, pin: bool=False, boost: float=1e9):
        self.overrides, self.base, self.pin, self.boost = overrides, base, pin, boost
    def score(self, qid: str, label: str) -> float:
        s = self.base.score(qid, label)
        if any(label == v or qid == k for k,v in self.overrides.items()):
            return self.boost if self.pin else s + self.boost
        return s
