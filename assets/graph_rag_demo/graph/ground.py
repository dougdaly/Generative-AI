import re
from typing import Dict, Set, Iterable, Tuple

def detect_entities(q: str):
    ql = q.lower()
    hits = []
    for term, (typ, key) in SYN.items():
        if term in ql:
            hits.append((typ, key))
    for m in re.findall(r"[A-Z][0-9][0-9]\.[0-9A-Z]{1,2}", q):
        hits.append(("Diagnosis", m))
    return list(set(hits))

# Expecting synonyms as a list of (term, kind, code)
# kind ∈ {"Procedure","Diagnosis","Modifier"}
def ground(query: str, synonyms: Iterable[Tuple[str,str,str]] = None) -> Dict[str, Set[str]]:
    """
    Return typed seed codes:
      {"procedures": {...}, "diagnoses": {...}, "modifiers": {...}}
    Only codes whose 'term' appears in the query (case-insensitive) are included.
    """
    q = " " + re.sub(r"\s+", " ", query.lower()) + " "
    px, dx, md = set(), set(), set()

    # Allow injecting synonyms at call-time OR import from engine
    if synonyms is None:
        try:
            from .engine import GraphRAG  # optional fallback
        except Exception:
            synonyms = []
        else:
            # if you really want, you can wire this up via a global/engine
            synonyms = []  # better: pass explicitly eng.syn

    for term, kind, code in synonyms:
        t = f" {term.strip().lower()} "
        if t in q:
            if kind == "Procedure":
                px.add(code)
            elif kind == "Diagnosis":
                dx.add(code)
            elif kind == "Modifier":
                md.add(code)

    return {"procedures": px, "diagnoses": dx, "modifiers": md}
