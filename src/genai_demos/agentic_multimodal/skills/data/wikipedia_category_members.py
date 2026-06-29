# skills/data/wikipedia_category_members.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import random

@dataclass(frozen=True)
class NamedItem:
    qid: str
    name: str

@dataclass(frozen=True)
class CatalogItem:
    qid: str
    name: str
    item_type: str
    group: str | None = None
    description: str | None = None
    image_url: str | None = None
    wikipedia_url: str | None = None

def _category_query(category_title: str, limit: int) -> str:
    # category_title must look like "Category:Mammals"
    return f"""
PREFIX schema: <http://schema.org/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX mwapi: <https://www.mediawiki.org/ontology#API/>

SELECT ?item ?itemLabel WHERE {{
  SERVICE wikibase:mwapi {{
    bd:serviceParam wikibase:endpoint "en.wikipedia.org";
                    wikibase:api "Generator";
                    mwapi:generator "categorymembers";
                    mwapi:gcmtitle "{category_title}";
                    mwapi:gcmlimit "{limit}";
                    mwapi:gcmnamespace "0".
    ?title wikibase:apiOutput mwapi:title .
  }}

  ?enwiki schema:name ?title ;
          schema:about ?item ;
          schema:isPartOf <https://en.wikipedia.org/> .

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
""".strip()

def fetch_from_categories(registry, *, categories: list[str], count: int, seed: str, pool_per_cat: int = 250) -> List[NamedItem]:
    # Pull a pool from each category, dedupe, shuffle, take N.
    rows = []
    for cat in categories:
        q = _category_query(cat, pool_per_cat)
        rows.extend(registry.sparql.run(q))

    seen = set()
    items: list[NamedItem] = []
    for r in rows:
        uri = r["item"]["value"]
        qid = uri.rsplit("/", 1)[-1]
        name = r["itemLabel"]["value"]
        key = (qid, name)
        if key in seen:
            continue
        seen.add(key)
        items.append(NamedItem(qid=qid, name=name))

    rng = random.Random(str(seed))
    rng.shuffle(items)
    return items[:count]

