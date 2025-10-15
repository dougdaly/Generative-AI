import re
from typing import Dict, Set, Iterable, Tuple
from .params import ICD_RE, CPT_RE, norm_code


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

    return enrich_ground(query, {"procedures": px, "diagnoses": dx, "modifiers": md})


def enrich_ground(query: str, raw: dict) -> dict:
    """
    Make 'raw' robust by scraping explicit codes from the query and
    ensuring both specific & family ICDs can flow downstream.
    """
    raw = raw or {}
    procs  = set(raw.get("procedures") or [])
    dxs    = set(raw.get("diagnoses") or [])
    mods   = set(raw.get("modifiers")  or [])

    # 1) Scrape explicit codes from the query
    for tok in ICD_RE.findall(query):
        dxs.add(norm_code(tok))
    for tok in CPT_RE.findall(query):
        procs.add(tok.strip())

    # 2) Ensure codes exist as strings (your _iter_grounded handles strings fine)
    #    Keep both specifics (M75.41) and families (M75.0x) if present.
    #    No dedup needed beyond set().

    return {"procedures": procs, "diagnoses": dxs, "modifiers": mods}