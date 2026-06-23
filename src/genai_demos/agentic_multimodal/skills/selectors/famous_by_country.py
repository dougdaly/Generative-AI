# skills/selectors/famous_by_country.py
from __future__ import annotations
from typing import Dict, Iterable, List, Optional
from dataclasses import dataclass

from agentic_multimodal.schemas.entities import Person   # reuse your Person
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import _to_iso_or_none  # reuse util
from agentic_multimodal.skills.geo import GeoProvider     # same base you used for geo sets

# --- constants at top of file ---
DEFAULT_WEIGHTS = {"pv": 0.60, "affinity": 0.25, "image": 0.15}
# affinity was 1 or 2; normalize to 0..1 via (affinity-1)/1

def _blend_scores(scored: list[dict], w: dict | None = None) -> list[dict]:
    """Blend pageview/sitelink score + affinity + image-presence into one rank."""
    if not scored:
        return scored
    w = {**DEFAULT_WEIGHTS, **(w or {})}

    # pageview path sets "score"; sitelinks path sets "score" too (count)
    # normalize pv/sitelinks score to 0..1 per batch
    smax = max(float(s.get("score", 0.0)) for s in scored) or 1.0
    for s in scored:
        pv_norm = float(s.get("score", 0.0)) / smax
        aff_raw = int(float(s.get("affinity", 0)))         # 1 (citizenship) or 2 (represents)
        aff_norm = max(0.0, min(1.0, (aff_raw - 1) / 1.0)) # 0 or 1
        has_img = 1.0 if s.get("image_url") else 0.0
        s["score_blended"] = (
            w["pv"] * pv_norm +
            w["affinity"] * aff_norm +
            w["image"] * has_img
        )
    scored.sort(key=lambda x: (x.get("score_blended", 0.0), x.get("score", 0.0)), reverse=True)
    return scored


# QIDs
Q_HUMAN = "Q5"
P_OCCUPATION  = "P106"
P_COUNTRY_CIT = "P27"   # country of citizenship
P_REPRESENTS  = "P1532" # country for sport
P_IMAGE       = "P18"
# (Sometimes “native of” P1036, “place of birth” P19 can be useful but we’ll keep it strict.)

# Category → occupation QIDs (minimal, expand as needed)
CATEGORY_OCCS: Dict[str, List[str]] = {
    "sports": [
        "Q2066131",   # athlete / sportsperson (broad)
        "Q937857",    # association football player
        "Q3665646",   # basketball player
        "Q10833314",  # tennis player
        "Q1336152",   # motorsport racing driver
        "Q13474373",  # boxer
        "Q19204627",  # mixed martial artist
        "Q11774891",  # ice hockey player
        "Q13141064",  # alpine skier
        # toss in others you care about
    ],
    "musicians": [
        "Q639669",   # singer
        "Q753110",   # songwriter
        "Q36834",    # composer
        "Q488205",   # rapper
        "Q36811",    # musician (generic)
    ],
    "actors": [
        "Q33999",    # actor
        "Q10800557", # film actor
        "Q2259451",  # television actor
    ],
    "scientists": [
        "Q901",      # scientist
        "Q170790",   # physicist
        "Q2329",     # chemist
        "Q441",      # biologist
        "Q1650915",  # computer scientist
    ],
}

def _vals(qids: Iterable[str]) -> str:
    return " ".join(f"wd:{str(q).lstrip('wd:')}" for q in qids)

def _v(b, k):
    x = b.get(k);  return x.get("value") if isinstance(x, dict) else None



@dataclass
class FamousPersonsByCountry(GeoProvider):
    key: str   = "famous_by_country"
    title: str = "Country → famous persons (by occupation & score)"
    # Generic: famous persons for a country, filtered by occupation(s) + ranked by popularity.
    # Persons are linked by citizenship (P27) or represents (P1532) -- preference is 'represents'.
    def fetch(
        self,
        client: WikidataSPARQL,
        *,
        language: str = "en",
        country_qid: str,
        category: Optional[str] = None,
        occ_qids: Optional[Iterable[str]] = None,
        sport_qids: Optional[Iterable[str]] = None,
        limit_candidates: int = 60,
        score: str = "pageviews",
        days: int = 90,
    ) -> List[Person]:
        occs: List[str] = []
        if category:
            occs.extend(CATEGORY_OCCS.get(category, []))
        if occ_qids:
            occs.extend([str(q) for q in occ_qids])
        occs = list(dict.fromkeys(occs))

        occ_filter = f"?person wdt:{P_OCCUPATION} ?occ . VALUES ?occ {{ {_vals(occs)} }} ." if occs else ""
        sport_filter = f"?person wdt:P641 ?sport . VALUES ?sport {{ {_vals(sport_qids)} }} ." if sport_qids else ""

        # Prefer represents (P1532) over citizenship (P27) via affinity=2 vs 1, then GROUP BY
        q = f"""
        PREFIX wd:        <http://www.wikidata.org/entity/>
        PREFIX wdt:       <http://www.wikidata.org/prop/direct/>
        PREFIX wikibase:  <http://wikiba.se/ontology#>
        PREFIX schema:    <http://schema.org/>
        PREFIX rdfs:      <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?person ?name ?image (MAX(?aff) AS ?affinity) WHERE {{
        {{
            SELECT ?person ?name ?image ?aff WHERE {{
            ?person wdt:P31 wd:{Q_HUMAN} .
            {occ_filter}
            {sport_filter}

            {{ ?person wdt:{P_REPRESENTS} wd:{country_qid} . BIND(2 AS ?aff) }}
            UNION
            {{ ?person wdt:{P_COUNTRY_CIT} wd:{country_qid} . BIND(1 AS ?aff) }}

            OPTIONAL {{ ?person wdt:{P_IMAGE} ?image . }}

            # Require/collect sitelinks so we can filter low-notability
            ?person wikibase:sitelinks ?links .
            FILTER(?links >= 20)

            # A) English Wikipedia (optional but preferred)
            OPTIONAL {{
                ?enArticle schema:about ?person ;
                        schema:isPartOf <https://en.wikipedia.org/> ;
                        schema:name ?wpTitleEn .
            }}

            # B) Any Wikipedia (fallback)
            OPTIONAL {{
                ?anyArticle schema:about ?person ;
                            schema:isPartOf [ wikibase:wikiGroup "wikipedia" ] ;
                            schema:name ?wpTitleAny .
            }}

            # Labels
            OPTIONAL {{ ?person rdfs:label ?lblEn  . FILTER(LANG(?lblEn) = "en") }}
            OPTIONAL {{ ?person rdfs:label ?lblAny . FILTER(LANG(?lblAny) != "") }}

            # Final name preference
            BIND(
                COALESCE(?lblEn, ?lblAny, ?wpTitleEn, ?wpTitleAny, STRAFTER(STR(?person), "/entity/"))
                AS ?name
            )
            }}
            LIMIT {int(limit_candidates)}
        }}
        }}
        GROUP BY ?person ?name ?image
        """

        rows = client.sparql.run(q)
        print(rows)
        cands = []
        for r in rows:
            uri = _v(r, "person");  qid = uri.rsplit("/",1)[-1] if uri else None
            if not qid:
                continue
            name = _v(r, "name") or qid
            img  = _v(r, "image")
            aff  = int(float(_v(r, "affinity") or "0"))
            cands.append({"qid": qid, "label": name, "image_url": img, "affinity": aff})

        # Popularity scoring (you already have the plumbing)
        if score == "pageviews":
            scored = _score_by_pageviews(cands, days=days)
        elif score == "sitelinks":
            scored = _score_by_sitelinks(client, cands)
        elif score == "blended":  # NEW path
            base = _score_by_pageviews(cands, days=days)
            scored = _blend_scores(base)
        else:
            # raw pass-through (no ranking)
            scored = cands

        # Final rank (if not blended): keep your affinity > popularity rule
        if score != "blended":
            scored.sort(key=lambda x: (x.get("affinity", 0), x.get("score", 0)), reverse=True)

        return [Person(qid=s["qid"], name=s["label"], image_url=s.get("image_url"), terms=[]) for s in scored]


def _score_by_pageviews(cands: List[Dict], *, days:int=90) -> List[Dict]:
    """
    Implement using your existing pageviews cache/fetcher.
    - Try enwiki first; fallback to native language title if you store it.
    - Sum last `days`; timeout & retry; memoize for a week.
    """
    # placeholder stub: keep stable order for now
    out = []
    for i, c in enumerate(cands):
        out.append({**c, "score": 1000 - i})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out

def _score_by_sitelinks(client: WikidataSPARQL, cands: List[Dict]) -> List[Dict]:
    if not cands: 
        return []
    values = " ".join(f"wd:{c['qid']}" for c in cands)
    q = f"""
    SELECT ?item (COUNT(?site) AS ?links) WHERE {{
      VALUES ?item {{ {values} }}
      ?item ?p ?o .
      FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct-sitelinks/"))
      BIND(?o AS ?site)
    }}
    GROUP BY ?item
    """
    rows = client.sparql.run(q)  # ← change
    counts = { r["item"]["value"].rsplit("/",1)[-1]: int(float(r["links"]["value"])) for r in rows }
    scored = [{**c, "score": counts.get(c["qid"], 0)} for c in cands]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored

