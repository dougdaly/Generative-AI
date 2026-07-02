from __future__ import annotations

from typing import Dict, List, Optional

from agentic_multimodal.schemas.entities import Person, OfficeTerm
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import SeriesProvider, _to_iso_or_none
from agentic_multimodal.skills.series.labels import (
    deterministic_language,
    ensure_qid,
    fetch_entity_labels_and_images,
)


def _v(binding: Dict, key: str) -> Optional[str]:
    value = binding.get(key)
    return value.get("value") if isinstance(value, dict) else None


class AwardProvider(SeriesProvider):
    key = "award"
    title = "Award recipients"

    def fetch(
        self,
        client: WikidataSPARQL,
        *,
        language: str = "en",
        award_qid: str,
        restrict_to_subaward_qids: Optional[List[str]] = None,
    ) -> List[Person]:
        base = ensure_qid(award_qid)
        if restrict_to_subaward_qids:
            sub_vals = " ".join(f"wd:{ensure_qid(x)}" for x in restrict_to_subaward_qids)
            filter_clause = f"VALUES ?award {{ {sub_vals} }}"
        else:
            filter_clause = f"VALUES ?award {{ wd:{base} }}"

        label_language = deterministic_language(language)

        q = f"""
        # agentic_multimodal_award_terms_v3
        SELECT ?person ?when WHERE {{
          {filter_clause}
          ?person wdt:P31 wd:Q5 .
          ?person p:P166 ?stmt .
          ?stmt ps:P166 ?award .
          OPTIONAL {{ ?stmt pq:P585 ?when . }}
        }}
        ORDER BY ?when ?person
        """
        rows = client.run(q)

        terms_by_qid: dict[str, list[OfficeTerm]] = {}
        for row in rows:
            uri = _v(row, "person")
            if not uri:
                continue
            qid = ensure_qid(uri)
            when = _to_iso_or_none(_v(row, "when"))
            terms_by_qid.setdefault(qid, []).append(OfficeTerm(start=when, end=None))

        qids = list(terms_by_qid)
        entity_meta = fetch_entity_labels_and_images(client, qids, language=label_language)

        people = [
            Person(
                qid=qid,
                name=entity_meta.get(qid, {}).get("label") or qid,
                image_url=entity_meta.get(qid, {}).get("image_url"),
                terms=terms,
            )
            for qid, terms in terms_by_qid.items()
        ]

        def _key(person: Person):
            starts = [term.start for term in person.terms if term.start]
            earliest = min(starts) if starts else None
            return (earliest is None, earliest or "9999-12-31", person.name)

        people.sort(key=_key)
        return people
