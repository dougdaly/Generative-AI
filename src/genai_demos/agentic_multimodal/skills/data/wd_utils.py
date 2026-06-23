# skills/data/wd_utils.py
from typing import Dict, List
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL

def fetch_labels_en_or_latin(client: WikidataSPARQL, qids: List[str], chunk: int = 25) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i in range(0, len(qids), chunk):
        batch = qids[i:i+chunk]
        values = " ".join(f"wd:{q}" for q in batch)
        q = f"""
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        SELECT ?item ?lab WHERE {{
          VALUES ?item {{ {values} }}
          OPTIONAL {{ ?item rdfs:label  ?en  . FILTER(LANGMATCHES(LANG(?en),'en'))  }}
          OPTIONAL {{ ?item schema:name ?en2 . FILTER(LANGMATCHES(LANG(?en2),'en')) }}
          OPTIONAL {{ ?item rdfs:label  ?ls  . FILTER(REGEX(STR(?ls),  '^[A-Za-z]')) }}
          OPTIONAL {{ ?item schema:name ?ls2 . FILTER(REGEX(STR(?ls2), '^[A-Za-z]')) }}
          BIND(COALESCE(?en, ?en2, ?ls, ?ls2) AS ?lab)
        }}
        """
        rows = client.run(q)
        for r in rows:
            qid = r["item"]["value"].rpartition("/")[2]
            lab = r.get("lab", {}).get("value")
            if lab: out[qid] = lab
    return out

