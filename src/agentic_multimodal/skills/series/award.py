from typing import Dict, List, Optional
from agentic_multimodal.schemas.entities import Person, OfficeTerm
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import SeriesProvider, _to_iso_or_none

def _v(b: Dict, k: str) -> Optional[str]:
    v = b.get(k);  return v.get("value") if isinstance(v, dict) else None

def _ensure_qid(x: str) -> str:
    # tolerant of full URIs or bare QIDs
    return x.rsplit("/", 1)[-1]

class AwardProvider(SeriesProvider):
    key   = "award"
    title = "Award recipients"

    def fetch(
        self,
        client: WikidataSPARQL,
        *,
        language: str = "en",
        award_qid: str,
        restrict_to_subaward_qids: Optional[List[str]] = None
    ) -> List[Person]:
        base = _ensure_qid(award_qid)
        if restrict_to_subaward_qids:
            sub_vals = " ".join(f"wd:{_ensure_qid(x)}" for x in restrict_to_subaward_qids)
            filter_clause = f"VALUES ?award {{ {sub_vals} }}"
        else:
            filter_clause = f"VALUES ?award {{ wd:{base} }}"

        q = f"""
        SELECT ?person ?personLabel ?image ?when WHERE {{
          {filter_clause}
          ?person wdt:P31 wd:Q5 .
          ?person p:P166 ?stmt .
          ?stmt ps:P166 ?award .
          OPTIONAL {{ ?stmt pq:P585 ?when . }}
          OPTIONAL {{ ?person wdt:P18 ?image . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}". }}
        }}
        ORDER BY ?when ?personLabel
        """
        rows = client.run(q)

        # group by person
        people_by_qid: Dict[str, Person] = {}
        for b in rows:
            uri = _v(b, "person");  qid = _ensure_qid(uri) if uri else None
            if not qid: continue
            name = _v(b, "personLabel") or qid
            img  = _v(b, "image")
            when = _to_iso_or_none(_v(b, "when"))

            if qid not in people_by_qid:
                people_by_qid[qid] = Person(qid=qid, name=name, image_url=img, terms=[])
            # award is a point; put in start; leave end None
            people_by_qid[qid].terms.append(OfficeTerm(start=when, end=None))

        people = list(people_by_qid.values())

        # sort by earliest award date, then name
        def _key(p: Person):
            starts = [t.start for t in p.terms if t.start]
            earliest = min(starts) if starts else None
            return (earliest is None, earliest or "9999-12-31", p.name)

        people.sort(key=_key)
        return people

