"""
Lightweight Wikidata SPARQL client + helpers.

Designed for small, fast utilities inside your RAG/Graph workflows.
- Minimal deps (requests only)
- Friendly dict outputs (no SPARQL JSON ceremony)
- Retry + backoff, polite User-Agent
- Convenience helpers for labels, descriptions, claims, and series membership

Usage
-----
from data.wikidata_sparql import run, get_labels, get_claim_values, series_members
rows = run('''
SELECT ?item ?itemLabel WHERE {
  ?item wdt:P31 wd:Q5 .
  ?item wdt:P106 wd:Q82955 . # ballet dancer
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} LIMIT 5
''')
print(rows)

# Labels for Q-ids
print(get_labels(["Q42", "Q1"]))

# Claim values (e.g., countries for a list of Q-ids)
print(get_claim_values(["Q30", "Q142"], prop="P36"))  # capital

# Series members (e.g., U.S. presidents Q11696 via P179)
print(series_members("Q11696", limit=10))
"""
from __future__ import annotations

import os
import time
import logging
from typing import Dict, Iterable, List, Optional, Sequence
import requests

from dataclasses import dataclass
import requests
from typing import List, Dict

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "agentic-multimodal/0.1 (WikidataSPARQL client)"
}

@dataclass
class WikidataHTTPError(Exception):
    status: int
    text: str

class WikidataSPARQL:
    def __init__(self, endpoint: str = WIKIDATA_SPARQL_URL, headers: Dict[str, str] = None, timeout: int = 30):
        self.endpoint = endpoint
        self.headers = headers or HEADERS
        self.timeout = timeout

    def run(self, query: str) -> List[Dict]:
        r = requests.get(self.endpoint, params={"query": query, "format": "json"},
                         headers=self.headers, timeout=self.timeout)
        if r.status_code != 200:
            raise WikidataHTTPError(r.status_code, r.text)
        data = r.json()
        return data.get("results", {}).get("bindings", [])



# ---- Config ----
ENDPOINT = os.environ.get("WD_SPARQL_ENDPOINT", "https://query.wikidata.org/sparql")
USER_AGENT = os.environ.get(
    "WD_USER_AGENT",
    "GraphRAG-WDClient/0.1 (contact: youremail@example.com)",
)
TIMEOUT = float(os.environ.get("WD_TIMEOUT", 60))
MAX_RETRIES = int(os.environ.get("WD_MAX_RETRIES", 4))
BACKOFF = float(os.environ.get("WD_BACKOFF", 1.25))

log = logging.getLogger(__name__)

class WDSparqlError(RuntimeError):
    pass

# ---- Core request ----
def _request(query: str) -> Dict:
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    params = {"query": query}

    delay = 0.0
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        if delay:
            time.sleep(delay)
        try:
            resp = requests.get(ENDPOINT, params=params, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 429:
                # too many requests — backoff and retry
                delay = max(delay * BACKOFF, 1.0) if delay else 1.0
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # network, timeout, HTTP >= 400
            last_exc = e
            delay = max(delay * BACKOFF, 0.8) if delay else 0.8
    raise WDSparqlError(f"SPARQL request failed after {MAX_RETRIES} tries: {last_exc}")

# ---- Value coercion ----
def _coerce(binding: Dict) -> Dict:
    out: Dict[str, object] = {}
    for k, v in binding.items():
        t = v.get("type")
        val = v.get("value")
        if t == "uri" and val and val.startswith("http://www.wikidata.org/entity/"):
            out[k] = val.rsplit("/", 1)[-1]  # Q-id
        elif t == "literal":
            out[k] = val
        elif t == "bnode":
            out[k] = val
        else:
            out[k] = val
    return out

# ---- Public: run a SPARQL query and get list[dict] ----
def run(query: str) -> List[Dict[str, object]]:
    data = _request(query)
    results = data.get("results", {}).get("bindings", [])
    return [_coerce(b) for b in results]

# ---- Helpers ----
def _values_clause(var: str, qids: Sequence[str]) -> str:
    vals = " ".join(f"wd:{qid}" for qid in qids)
    return f"VALUES ?{var} {{ {vals} }}"

def get_labels(qids: Sequence[str], lang: str = "en", include_descriptions: bool = True) -> Dict[str, Dict[str, str]]:
    if not qids:
        return {}
    qids = list(dict.fromkeys(qids))  # dedupe, preserve order
    clause = _values_clause("id", qids)
    desc = "?idDescription" if include_descriptions else ""
    q = f"""
    SELECT ?id ?idLabel {desc} WHERE {{
      {clause}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
    }}
    """
    rows = run(q)
    out: Dict[str, Dict[str, str]] = {qid: {} for qid in qids}
    for r in rows:
        qid = r.get("id")
        if isinstance(qid, str):
            d = out.setdefault(qid, {})
            if "idLabel" in r:
                d["label"] = str(r["idLabel"])
            if include_descriptions and "idDescription" in r:
                d["description"] = str(r["idDescription"])
    return out

def get_claim_values(qids: Sequence[str], prop: str) -> Dict[str, List[str]]:
    """Return object Q-ids (or literal strings) for a property.
    Example: get_claim_values(["Q30"], "P36") -> {"Q30": ["Q60"]}  # USA -> capital -> Washington, D.C.
    """
    if not qids:
        return {}
    clause = _values_clause("s", qids)
    q = f"""
    SELECT ?s ?o WHERE {{
      {clause}
      OPTIONAL {{ ?s wdt:{prop} ?o }}
    }}
    """
    rows = run(q)
    out: Dict[str, List[str]] = {qid: [] for qid in qids}
    for r in rows:
        s = r.get("s")
        o = r.get("o")
        if isinstance(s, str) and o is not None:
            out.setdefault(s, []).append(str(o))
    return out

def series_members(series_qid: str, limit: int = 1000, lang_chain: str = "[AUTO_LANGUAGE],en") -> List[Dict[str, object]]:
    """
    Items where ?item wdt:P179 wd:<series_qid> (part of a series).
    Returns both ?item and ?label where ?label always resolves (falls back to QID).
    """
    q = f"""
    SELECT ?item ?label WHERE {{
      ?item wdt:P179 wd:{series_qid} .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang_chain}" . }}
      # Fallback: if ?itemLabel is missing, use the QID tail
      BIND( COALESCE(?itemLabel, STRAFTER(STR(?item), "/entity/")) AS ?label )
    }}
    ORDER BY ?label
    LIMIT {int(limit)}
    """
    return run(q)

def neighbors(qids: Sequence[str], props: Sequence[str], direction: str = "out", limit_per: int = 50) -> List[Dict[str, object]]:
    """Get neighbors via given properties.
    direction: 'out' => qid -P-> neighbor; 'in' => neighbor -P-> qid
    """
    if not qids or not props:
        return []
    clause = _values_clause("a", qids)
    prop_filter = "(" + "|".join(f"wdt:{p}" for p in props) + ")"
    if direction == "out":
        triple = f"?a {prop_filter} ?b"
    else:
        triple = f"?b {prop_filter} ?a"
    q = f"""
    SELECT ?a ?b WHERE {{
      {clause}
      {triple} .
    }} LIMIT {int(limit_per) * max(1, len(qids))}
    """
    return run(q)

# Quick, safe sleep for etiquette between high-volume calls
_def_sleep = float(os.environ.get("WD_SLEEP", 0))

def polite_pause():
    if _def_sleep > 0:
        time.sleep(_def_sleep)

__all__ = [
    "run",
    "get_labels",
    "get_claim_values",
    "series_members",
    "neighbors",
    "WDSparqlError",
    "polite_pause",
    "WikidataSPARQL", 
    "WikidataHTTPError"]
