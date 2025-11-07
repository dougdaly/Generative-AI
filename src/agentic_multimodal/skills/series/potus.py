# provider for Presidents of the United States
from typing import Dict, List, Optional
from agentic_multimodal.schemas.entities import Person, OfficeTerm
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import SeriesProvider, _to_iso_or_none

QID_POTUS = "Q11696"   # office: President of the United States (P39)

def _get_val(b: Dict, key: str) -> Optional[str]:
    v = b.get(key)
    return v.get("value") if isinstance(v, dict) else None

class POTUSProvider(SeriesProvider):
    key   = "potus"
    title = "U.S. Presidents"

    def fetch(self, client: WikidataSPARQL, *, language: str = "en") -> List[Person]:
        q = f"""
        SELECT ?person ?personLabel ?image ?start ?end WHERE {{
          ?person p:P39 ?stmt .
          ?stmt ps:P39 wd:{QID_POTUS} .
          OPTIONAL {{ ?person wdt:P18 ?image . }}
          OPTIONAL {{ ?stmt pq:P580 ?start . }}
          OPTIONAL {{ ?stmt pq:P582 ?end   . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}". }}
        }}
        ORDER BY ?start
        """
        rows = client.run(q)

        by_qid: Dict[str, Person] = {}
        first_start: Dict[str, Optional[str]] = {}

        for b in rows:
            uri = _get_val(b, "person")
            if not uri:
                continue
            qid = uri.rsplit("/", 1)[-1]
            name = _get_val(b, "personLabel") or qid
            img  = _get_val(b, "image")
            start = _to_iso_or_none(_get_val(b, "start"))
            end   = _to_iso_or_none(_get_val(b, "end"))

            if qid not in by_qid:
                by_qid[qid] = Person(qid=qid, name=name, image_url=img, terms=[])
                first_start[qid] = start
            by_qid[qid].terms.append(OfficeTerm(start=start, end=end))
            if start and (first_start[qid] is None or start < first_start[qid]):
                first_start[qid] = start

        people = list(by_qid.values())

        def _key(p: Person):
            starts = [t.start for t in p.terms if t.start]
            earliest = min(starts) if starts else None
            return (earliest is None, earliest or "9999-12-31", p.name)

        people.sort(key=_key)
        return people

