"""
Wikidata label search helpers using the MediaWiki API (wbsearchentities).

Quick use:
    from data.wikidata_search_label import search_labels, best_qid, get_entity_summaries
    hits = search_labels("Marie Curie", limit=5)
    qid = best_qid("Marie Curie").qid
    summaries = get_entity_summaries([qid])

No third‑party deps; just `requests`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
import time
import urllib.parse
import requests

API_URL = "https://www.wikidata.org/w/api.php"
UA = "wd-search-label/1.0 (edu demo; mailto:example@example.com)"

# --- Models -----------------------------------------------------------------

@dataclass
class SearchHit:
    qid: str
    label: str
    description: str
    match_score: float  # 0..1 heuristic (API provides quality; we normalize)
    aliases: List[str]
    language: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "qid": self.qid,
            "label": self.label,
            "description": self.description,
            "match_score": self.match_score,
            "aliases": self.aliases,
            "language": self.language,
        }

@dataclass
class EntitySummary:
    qid: str
    label: str
    description: str
    aliases: List[str]
    sitelinks: Dict[str, str]  # e.g., {"enwiki": "https://en.wikipedia.org/wiki/..."}

    def as_dict(self) -> Dict[str, object]:
        return {
            "qid": self.qid,
            "label": self.label,
            "description": self.description,
            "aliases": self.aliases,
            "sitelinks": self.sitelinks,
        }

# --- Core HTTP --------------------------------------------------------------

def _get(params: Dict[str, str], *, retries: int = 3, backoff: float = 0.6) -> dict:
    headers = {"User-Agent": UA}
    for attempt in range(retries):
        try:
            r = requests.get(API_URL, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))
    # not reached
    return {}

# --- Public API -------------------------------------------------------------

def search_labels(
    query: str,
    *,
    language: str = "en",
    limit: int = 10,
    entity_type: str = "item",
) -> List[SearchHit]:
    """Search Wikidata labels/descriptions for items matching `query`.

    Uses wbsearchentities; returns normalized SearchHit objects.
    """
    if not query or not query.strip():
        return []

    params = {
        "action": "wbsearchentities",
        "format": "json",
        "language": language,
        "uselang": language,
        "type": entity_type,
        "search": query,
        "limit": str(limit),
    }
    data = _get(params)
    results = []
    for e in data.get("search", []):
        qid = e.get("id", "")
        label = e.get("label", "") or ""
        desc = e.get("description", "") or ""
        # Heuristic score normalization: API may include a numeric "score" or "match" detail
        raw_score = 0.0
        if isinstance(e.get("score"), (int, float)):
            raw_score = float(e["score"])  # unbounded; we'll squash
        # simple squash 1 - 1/(1+score) to map [0,inf) -> [0,1)
        score = 1.0 - 1.0 / (1.0 + max(0.0, raw_score))

        aliases = []
        # wbsearchentities returns aliases inside "aliases" of each search result sometimes
        if isinstance(e.get("aliases"), list):
            aliases = [a for a in e["aliases"] if isinstance(a, str)]

        # Defensive filter: keep only QIDs
        if not qid.startswith("Q"):
            continue

        results.append(
            SearchHit(
                qid=qid,
                label=label,
                description=desc,
                match_score=round(score, 3),
                aliases=aliases,
                language=language,
            )
        )
    return results


def best_qid(query: str, *, language: str = "en", prefer_exact: bool = True) -> Optional[SearchHit]:
    """Return the top SearchHit, biasing for exact or case‑insensitive label matches when present."""
    hits = search_labels(query, language=language, limit=25)
    if not hits:
        return None

    q_lower = query.strip().lower()

    def score(hit: SearchHit) -> Tuple[int, float]:
        lbl = (hit.label or "").lower()
        alias_hit = any((a or "").lower() == q_lower for a in hit.aliases)
        exact = int(lbl == q_lower or alias_hit)
        # primary key: exact match if requested, else 0; secondary: API score
        return (exact if prefer_exact else 0, hit.match_score)

    hits.sort(key=score, reverse=True)
    return hits[0]


def get_entity_summaries(qids: Iterable[str], *, language: str = "en") -> List[EntitySummary]:
    """Fetch labels/descriptions/aliases/sitelinks for QIDs via wbgetentities.

    Returns a list in the same order as input QIDs (missing items omitted).
    """
    filtered = [q for q in qids if isinstance(q, str) and q.startswith("Q")]
    if not filtered:
        return []

    params = {
        "action": "wbgetentities",
        "format": "json",
        "ids": "|".join(filtered),
        "props": "labels|descriptions|aliases|sitelinks/urls",
        "languages": language,
        "sitefilter": "enwiki|dewiki|frwiki|eswiki|itwiki|ptwiki|ruwiki|zhwiki|jawiki",
    }
    data = _get(params)
    entities = data.get("entities", {})

    out: List[EntitySummary] = []
    for q in filtered:
        ent = entities.get(q)
        if not ent:
            continue
        lbl = ent.get("labels", {}).get(language, {}).get("value", "")
        desc = ent.get("descriptions", {}).get(language, {}).get("value", "")
        alias_objs = ent.get("aliases", {}).get(language, [])
        aliases = [a.get("value", "") for a in alias_objs if isinstance(a, dict)]
        sitelinks = {}
        for key, sl in (ent.get("sitelinks") or {}).items():
            url = sl.get("url")
            if url:
                sitelinks[key] = url
        out.append(EntitySummary(qid=q, label=lbl, description=desc, aliases=aliases, sitelinks=sitelinks))
    return out

# --- Tiny CLI for quick tests ----------------------------------------------
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Wikidata label search")
    ap.add_argument("query", help="label to search")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    hits = search_labels(args.query, language=args.lang, limit=args.limit)
    for h in hits:
        print(h.as_dict())

    top = best_qid(args.query, language=args.lang)
    if top:
        print("\nBest:", top.as_dict())
        print("\nSummary:")
        print(get_entity_summaries([top.qid], language=args.lang)[0].as_dict())
