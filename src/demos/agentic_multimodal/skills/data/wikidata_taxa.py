# skills/data/wikidata_taxa.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Iterable

@dataclass(frozen=True)
class NamedItem:
    qid: str
    name: str


def _query_species_under(parent_qid: str, count: int, seed: str) -> str:
    """
    Return species under a parent taxon, limited to entries with an English Wikipedia page.
    This keeps results recognizable and avoids weird taxon-only stubs.
    """
    return f"""
SELECT ?item ?itemLabel WHERE {{
  ?item wdt:P105 wd:Q7432 .        # taxon rank: species
  ?item wdt:P171* wd:{parent_qid} .# parent taxon chain includes parent

  # Require an English Wikipedia sitelink
  ?enwiki schema:about ?item ;
         schema:isPartOf <https://en.wikipedia.org/> .

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY MD5(CONCAT(STR(?item), "{seed}"))
LIMIT {count}
""".strip()


def fetch_random_species(registry, *, parent_qid: str, count: int, seed: str) -> list[NamedItem]:
    """
    Uses registry.sparql to fetch a list[NamedItem(qid,name)].
    """
    sparql = registry.sparql

    # Support either .query() or .run() without guessing your internal method name.
    runner = getattr(sparql, "query", None) or getattr(sparql, "run", None)
    if runner is None:
        raise AttributeError("registry.sparql must expose .query(query) or .run(query)")

    rows = runner(_query_species_under(parent_qid, count, seed))

    out: list[NamedItem] = []
    for r in rows:
        uri = r["item"]["value"]  # "http://www.wikidata.org/entity/Qxxxx"
        qid = uri.rsplit("/", 1)[-1]
        name = r["itemLabel"]["value"]
        out.append(NamedItem(qid=qid, name=name))
    return out
