import requests, time, random
from typing import List, Dict


# This provides functions and parameters related to collecting information about a group of people.

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "agentic-multimodal/0.2 (+your_email@example.com)"}



def wd_sparql(query: str, retries: int = 4, timeout: int = 30) -> dict:
    last = None
    for i in range(retries):
        try:
            r = requests.post(
                WIKIDATA_SPARQL,
                data={"query": query},
                headers={"Accept":"application/sparql-results+json", **UA},
                timeout=timeout,
            )
            if r.status_code == 200:
                return r.json()
            # Show SPARQL error text when it’s a client/server error
            if r.status_code in (400, 404, 409, 500, 502, 503, 504, 429):
                # backoff for transient ones; otherwise raise with body
                if r.status_code in (429, 500, 502, 503, 504) and i < retries-1:
                    time.sleep((0.6*(2**i))*(1+0.25*random.random()))
                    continue
                try:
                    detail = r.text[:800]
                except Exception:
                    detail = "<no body>"
                raise requests.HTTPError(f"{r.status_code} from SPARQL endpoint:\n{detail}")
            r.raise_for_status()
        except requests.RequestException as e:
            last = e
            if i < retries-1:
                time.sleep((0.6*(2**i))*(1+0.25*random.random()))
                continue
            raise
    if last:
        raise last
    raise RuntimeError("SPARQL failed without exception")


def wd_search_label(term: str, limit: int = 5) -> List[Dict]:
    """Resolve labels to QIDs via wbsearchentities. Returns [{'id','label','description'}…]."""
    r = requests.get(
        WIKIDATA_SEARCH,
        params={
            "action": "wbsearchentities",
            "search": term,
            "language": "en",
            "format": "json",
            "type": "item",
            "limit": limit,
        },
        headers=UA,
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("search", [])

def ensure_qid(term_or_qid: str) -> str:
    """Accepts 'Q42' or a label like 'monarch of England' -> returns QID."""
    s = (term_or_qid or "").strip()
    if s.upper().startswith("Q") and s[1:].isdigit():
        return s
    hits = wd_search_label(s, limit=1)
    if not hits:
        raise ValueError(f"Could not resolve to QID: {term_or_qid!r}")
    return hits[0]["id"]

