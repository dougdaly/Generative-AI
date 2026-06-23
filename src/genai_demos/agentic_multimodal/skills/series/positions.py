from typing import Dict, List, Optional
from agentic_multimodal.schemas.entities import Person, OfficeTerm
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import SeriesProvider, _to_iso_or_none
from agentic_multimodal.skills.data.wd_utils import fetch_labels_en_or_latin

def _qid(u: str) -> str: return u.rpartition("/")[2]

class PositionsProvider(SeriesProvider):
    key = "positions"; title = "People by held positions"

    def fetch(
        self,
        client: WikidataSPARQL,
        *,
        position_qids: List[str],
        language: str = "[AUTO_LANGUAGE],en",  # kept for API symmetry
    ) -> List[Person]:
        vals = " ".join(f"wd:{q.lstrip('wd:')}" for q in position_qids)

        # 1) TERMS (cheap, with human filter)
        q_terms = f"""
        SELECT ?person ?start ?end WHERE {{
        ?person wdt:P31 wd:Q5 .           # ← keep only humans
        ?person p:P39 ?stmt .
        ?stmt ps:P39 ?pos .
        VALUES ?pos {{ {vals} }}
        OPTIONAL {{ ?stmt pq:P580 ?start . }}
        OPTIONAL {{ ?stmt pq:P582 ?end   . }}
        }}
        ORDER BY ?start
        """
        term_rows = client.run(q_terms)

        # build terms
        terms_by_qid = {}
        for r in term_rows:
            qid = _qid(r["person"]["value"])
            start = _to_iso_or_none(r.get("start", {}).get("value"))
            end   = _to_iso_or_none(r.get("end",   {}).get("value"))
            terms_by_qid.setdefault(qid, []).append(OfficeTerm(start=start, end=end))

        # 2) QIDs source of truth = from the terms you actually saw
        qids = sorted(set(_qid(r["person"]["value"]) for r in term_rows))

        # 3) fetch labels for those qids (unchanged)
        labels = fetch_labels_en_or_latin(client, qids)


        # 4) Assemble Persons (simple, deterministic)
        people = [
            Person(qid=qid, name=labels.get(qid, qid), image_url=None, terms=terms_by_qid.get(qid, []))
            for qid in qids
        ]

        # sort by earliest start
        def _key(p: Person):
            starts = [t.start for t in p.terms if t.start]
            earliest = min(starts) if starts else None
            return (earliest is None, earliest or "9999-12-31", p.name)
        people.sort(key=_key)

        return people
