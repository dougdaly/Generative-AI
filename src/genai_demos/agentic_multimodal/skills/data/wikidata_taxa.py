# skills/data/wikidata_taxa.py

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any


ANIMAL_CATALOG_PATH = Path("assets/catalogs/group_items/animals_us.json")


ANIMAL_CATEGORIES_US = {
    "mammal": "Category:Mammals of the United States",
    "bird": "Category:Birds of the United States",
    "reptile": "Category:Reptiles of the United States",
}


ANIMAL_WIKIDATA_CLASSES = {
    "mammal": "Q7377",
    "bird": "Q5113",
    "reptile": "Q10811",
}


def clean_title(title: str) -> str:
    # "Robin (bird)" -> "Robin"
    return re.sub(r"\s*\(.*\)\s*$", "", (title or "")).strip()

def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]

def wdqs_category_qids(registry, category_title: str, limit: int = 300) -> list[dict[str, Any]]:
    q = f"""
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX mwapi: <https://www.mediawiki.org/ontology#API/>
PREFIX bd: <http://www.bigdata.com/rdf#>

SELECT DISTINCT ?item ?wikiTitle WHERE {{
  SERVICE wikibase:mwapi {{
    bd:serviceParam wikibase:endpoint "en.wikipedia.org" ;
                    wikibase:api "Generator" ;
                    wikibase:limit "once" ;
                    mwapi:generator "categorymembers" ;
                    mwapi:gcmtitle "{category_title}" ;
                    mwapi:gcmnamespace "0" ;
                    mwapi:gcmlimit "{limit}" .
    ?item      wikibase:apiOutputItem mwapi:item .
    ?wikiTitle wikibase:apiOutput mwapi:title .
  }}

  FILTER(BOUND(?item))
}}
LIMIT {limit}
""".strip()

    return registry.sparql.run(q)


def wdqs_class_items(registry, root_qid: str, limit: int = 500) -> list[dict[str, Any]]:
    """
    Fallback query that does not rely on wikibase:mwapi category traversal.

    It asks for items that are instances of subclasses of the animal class,
    and requires an English Wikipedia page to keep results reasonably poster-friendly.
    """
    q = f"""
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX schema: <http://schema.org/>
PREFIX bd: <http://www.bigdata.com/rdf#>

SELECT DISTINCT ?item ?itemLabel ?article WHERE {{
  ?item wdt:P31/wdt:P279* wd:{root_qid} .

  ?article schema:about ?item ;
           schema:isPartOf <https://en.wikipedia.org/> .

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT {limit}
""".strip()

    return registry.sparql.run(q)


def wdqs_enrich_names(
    registry,
    qids: list[str],
    *,
    batch_size: int = 50,
) -> dict[str, dict[str, str | None]]:
    if not qids:
        return {}

    out: dict[str, dict[str, str | None]] = {}

    for batch in chunked(qids, batch_size):
        values = " ".join(f"wd:{qid}" for qid in batch)

        q = f"""
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX bd: <http://www.bigdata.com/rdf#>

SELECT ?item ?itemLabel ?commonName ?taxonName ?image WHERE {{
  VALUES ?item {{ {values} }}

  OPTIONAL {{ ?item wdt:P1843 ?commonName . FILTER(LANG(?commonName) = "en") }}
  OPTIONAL {{ ?item wdt:P225 ?taxonName }}
  OPTIONAL {{ ?item wdt:P18 ?image }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
""".strip()

        rows = registry.sparql.run(q)

        for row in rows:
            qid = row["item"]["value"].rsplit("/", 1)[-1]
            out[qid] = {
                "label": row.get("itemLabel", {}).get("value"),
                "common": row.get("commonName", {}).get("value"),
                "taxon": row.get("taxonName", {}).get("value"),
                "image_url": row.get("image", {}).get("value"),
            }

    return out


def build_animal_pool_from_categories(
    registry,
    *,
    categories: dict[str, str] = ANIMAL_CATEGORIES_US,
    limit_per_group: int = 350,
) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []

    for group, category in categories.items():
        rows = wdqs_category_qids(registry, category, limit=limit_per_group)

        for row in rows:
            qid = row["item"]["value"].rsplit("/", 1)[-1]
            title = clean_title(row.get("wikiTitle", {}).get("value", ""))

            if not title:
                continue

            pool.append(
                {
                    "qid": qid,
                    "wiki": title,
                    "group": group,
                    "source": "wikipedia_category",
                }
            )

    return dedupe_by_qid(pool)


def build_animal_pool_from_wikidata_classes(
    registry,
    *,
    classes: dict[str, str] = ANIMAL_WIKIDATA_CLASSES,
    limit_per_group: int = 500,
) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []

    for group, root_qid in classes.items():
        rows = wdqs_class_items(registry, root_qid, limit=limit_per_group)

        for row in rows:
            qid = row["item"]["value"].rsplit("/", 1)[-1]
            label = row.get("itemLabel", {}).get("value")

            if not label or label == qid:
                continue

            pool.append(
                {
                    "qid": qid,
                    "wiki": clean_title(label),
                    "group": group,
                    "source": "wikidata_class",
                }
            )

    return dedupe_by_qid(pool)


def dedupe_by_qid(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup: dict[str, dict[str, Any]] = {}

    for item in items:
        dedup.setdefault(item["qid"], item)

    return list(dedup.values())


def enrich_animal_items(registry, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = wdqs_enrich_names(registry, [item["qid"] for item in items])

    out: list[dict[str, Any]] = []

    for item in items:
        meta = enriched.get(item["qid"], {})

        display = (
            meta.get("common")
            or item.get("wiki")
            or meta.get("taxon")
            or meta.get("label")
            or item["qid"]
        )

        scientific = meta.get("taxon") or meta.get("label")

        out.append(
            {
                **item,
                "display": display,
                "scientific": scientific,
                "image_url": meta.get("image_url"),
            }
        )

    return out


def save_animal_pool(items: list[dict[str, Any]], path: str | Path = ANIMAL_CATALOG_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_animal_pool(path: str | Path = ANIMAL_CATALOG_PATH) -> list[dict[str, Any]]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_or_build_animal_pool(
    registry,
    *,
    path: str | Path = ANIMAL_CATALOG_PATH,
    force_rebuild: bool = False,
    limit_per_group: int = 500,
) -> list[dict[str, Any]]:
    path = Path(path)

    if path.exists() and not force_rebuild:
        return load_animal_pool(path)

    # First try the existing category strategy.
    pool = build_animal_pool_from_categories(
        registry,
        limit_per_group=limit_per_group,
    )

    # Fallback if wikibase:mwapi/category traversal returns nothing.
    if not pool:
        pool = build_animal_pool_from_wikidata_classes(
            registry,
            limit_per_group=limit_per_group,
        )

    if not pool:
        raise RuntimeError(
            "Could not build animal pool from Wikipedia categories or Wikidata classes."
        )

    # Important:
    # Save the raw pool only. Do not enrich the entire pool here.
    # Enrichment should happen only after selecting the final N items.
    save_animal_pool(pool, path)
    return pool