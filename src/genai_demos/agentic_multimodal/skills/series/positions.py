from __future__ import annotations

from typing import List

from agentic_multimodal.schemas.entities import Person, OfficeTerm
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import SeriesProvider, _to_iso_or_none
from agentic_multimodal.skills.series.labels import (
    deterministic_language,
    ensure_qid,
    fetch_entity_labels_and_images,
)


def _value(binding: dict, key: str) -> str | None:
    value = binding.get(key)
    return value.get("value") if isinstance(value, dict) else None


class PositionsProvider(SeriesProvider):
    key = "positions"
    title = "People by held positions"

    def fetch(
        self,
        client: WikidataSPARQL,
        *,
        position_qids: List[str],
        language: str = "en",
    ) -> List[Person]:
        """Fetch people who held one or more positions.

        This provider intentionally separates term retrieval from label/image
        retrieval. Term rows define the source of truth for membership and
        order. Labels/images are fetched by QID with an explicit language
        filter so public posters do not show localized labels or raw QIDs when
        Wikidata's auto-label service falls back poorly.
        """
        vals = " ".join(f"wd:{ensure_qid(q)}" for q in position_qids)
        label_language = deterministic_language(language)

        q_terms = f"""
        # agentic_multimodal_positions_terms_v3
        SELECT ?person ?start ?end WHERE {{
          ?person wdt:P31 wd:Q5 .
          ?person p:P39 ?stmt .
          ?stmt ps:P39 ?pos .
          VALUES ?pos {{ {vals} }}
          OPTIONAL {{ ?stmt pq:P580 ?start . }}
          OPTIONAL {{ ?stmt pq:P582 ?end . }}
        }}
        ORDER BY ?start ?end ?person
        """
        term_rows = client.run(q_terms)

        terms_by_qid: dict[str, list[OfficeTerm]] = {}
        for row in term_rows:
            person_uri = _value(row, "person")
            if not person_uri:
                continue
            qid = ensure_qid(person_uri)
            start = _to_iso_or_none(_value(row, "start"))
            end = _to_iso_or_none(_value(row, "end"))
            terms_by_qid.setdefault(qid, []).append(OfficeTerm(start=start, end=end))

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
