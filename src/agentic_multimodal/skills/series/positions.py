from typing import Dict, List, Optional
from agentic_multimodal.schemas.entities import Person, OfficeTerm
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import SeriesProvider, _to_iso_or_none

def _v(b: Dict, k: str) -> Optional[str]:
    v = b.get(k);  return v.get("value") if isinstance(v, dict) else None

def _ensure_qid(x: str) -> str:
    return x.rsplit("/", 1)[-1]

class PositionsProvider(SeriesProvider):
    key   = "positions"
    title = "People by held positions"

    def fetch(
        self,
        client: WikidataSPARQL,
        *,
        language: str = "en",
        position_qids: List[str]
    ) -> List[Person]:
        values = " ".join(f"wd:{_ensure_qid(q)}" for q in position_qids)
        q = f"""
        SELECT ?person ?personLabel ?image ?start ?end WHERE {{
          VALUES ?pos {{ {values} }}
          ?person wdt:P31 wd:Q5 .
          ?person p:P39 ?stmt .
          ?stmt ps:P39 ?pos .
          OPTIONAL {{ ?stmt pq:P580 ?start . }}
          OPTIONAL {{ ?stmt pq:P582 ?end   . }}
          OPTIONAL {{ ?person wdt:P18 ?image . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}". }}
        }}
        ORDER BY ?start
        """
        rows = client.run(q)

        by_qid: Dict[str, Person] = {}
        for b in rows:
            uri = _v(b, "person"); qid = _ensure_qid(uri) if uri else None
            if not qid: continue
            name = _v(b, "personLabel") or qid
            img  = _v(b, "image")
            start = _to_iso_or_none(_v(b, "start"))
            end   = _to_iso_or_none(_v(b, "end"))

            if qid not in by_qid:
                by_qid[qid] = Person(qid=qid, name=name, image_url=img, terms=[])
            by_qid[qid].terms.append(OfficeTerm(start=start, end=end))

        people = list(by_qid.values())

        def _key(p: Person):
            starts = [t.start for t in p.terms if t.start]
            earliest = min(starts) if starts else None
            return (earliest is None, earliest or "9999-12-31", p.name)

        people.sort(key=_key)
        return people

