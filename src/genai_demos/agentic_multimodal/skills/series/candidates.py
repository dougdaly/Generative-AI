from typing import List, Dict, Optional, Protocol
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL

def _v(b: Dict, k: str) -> Optional[str]:
    v = b.get(k);  return v.get("value") if isinstance(v, dict) else None
def _qid(uri: Optional[str]) -> Optional[str]:
    return uri.rsplit("/", 1)[-1] if uri else None

class CandidateProvider(Protocol):
    def candidates(self, client: WikidataSPARQL, *, country_qid: str, language: str="en") -> List[Dict]:
        ...

class AthletesByCitizenship(CandidateProvider):
    # humans with occupation subclass-of sportsperson (Q2066131)
    def candidates(self, client, *, country_qid, language="en"):
        q = f"""
        SELECT ?p ?pLabel ?image WHERE {{
          ?p wdt:P31 wd:Q5 ;
             wdt:P27 wd:{country_qid} ;
             wdt:P106/wdt:P279* wd:Q2066131 .
          OPTIONAL {{ ?p wdt:P18 ?image . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}" . }}
        }} LIMIT 200
        """
        rows = client.run(q)
        out = []
        for r in rows:
            qid = _qid(_v(r,"p"));  name=_v(r,"pLabel") or qid;  img=_v(r,"image")
            if qid: out.append({"qid": qid, "label": name, "image": img})
        return out

class CurrentNationalLeaders(CandidateProvider):
    """
    Current head of state OR head of government for the country.
    Pattern: person P39 position ?pos ; ?pos (P1001|P17) country ; no P582 end.
    Heads are subclasses of head of state (Q48352) or head of government (Q1622272).
    """
    def candidates(self, client, *, country_qid, language="en"):
        q = f"""
        SELECT ?p ?pLabel ?image WHERE {{
          VALUES ?root {{ wd:Q48352 wd:Q1622272 }}  # HoS/HoG roots
          ?p p:P39 ?stmt .
          ?stmt ps:P39 ?pos .
          FILTER EXISTS {{ ?pos wdt:P279* ?root . }}
          FILTER EXISTS {{ ?pos (wdt:P1001|wdt:P17) wd:{country_qid} . }}
          FILTER NOT EXISTS {{ ?stmt pq:P582 ?ended . }}
          OPTIONAL {{ ?p wdt:P18 ?image . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}" . }}
        }} LIMIT 20
        """
        rows = client.run(q)
        out = []
        for r in rows:
            qid = _qid(_v(r,"p"));  name=_v(r,"pLabel") or qid;  img=_v(r,"image")
            if qid: out.append({"qid": qid, "label": name, "image": img})
        return out
