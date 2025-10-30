from ..adapters.wikidata_series import ensure_qid, wd_sparql
from typing import List, Dict, Optional

def _norm_year(dt_iso: Optional[str]) -> str:
    if not dt_iso: return ""
    # dt looks like '1707-05-01T00:00:00Z'
    return dt_iso.split("-", 1)[0]

def _dedupe_span(items):
    """Group by (start,end), keep the shortest regnal-ish display name."""
    buckets = {}
    for it in items:
        key = (it.get("start",""), it.get("end",""))
        keep = buckets.get(key)
        if not keep or len(it["name"]) < len(keep["name"]):
            buckets[key] = it
    out = list(buckets.values())
    def yr(s): 
        try: return int(s) if s else 10**9
        except: return 10**9
    out.sort(key=lambda r: (yr(r["start"]), yr(r["end"])))
    return out


# ---------- SERIES BUILDERS ----------
def _yr(s, default=10**9):
    try: return int(s) if s else default
    except: return default

def _dedupe_series_rows(rows):
    # rows: [{"qid","name","start","end",...}]
    # 1) person+start merge (prefer informative end)
    by_ps = {}
    for r in rows:
        key = (r["qid"], r.get("start",""))
        prev = by_ps.get(key)
        if not prev:
            by_ps[key] = r
            continue
        # prefer non-empty end; if both, keep larger end year
        e, pe = r.get("end",""), prev.get("end","")
        if e and not pe:
            prev["end"] = e
        elif e and pe and _yr(e) > _yr(pe):
            prev["end"] = e
        # prefer shorter label
        if len(r["name"]) < len(prev["name"]):
            prev["name"] = r["name"]

    # 2) collapse by reign span (start,end), keep shortest name
    by_span = {}
    for r in by_ps.values():
        key = (r.get("start",""), r.get("end",""))
        prev = by_span.get(key)
        if not prev or len(r["name"]) < len(prev["name"]):
            by_span[key] = r

    out = list(by_span.values())
    out.sort(key=lambda x: (_yr(x.get("start")), _yr(x.get("end"))))
    return out


def series_by_positions(position_qids: list[str], title: str) -> dict:
    values = " ".join(f"wd:{ensure_qid(q)}" for q in position_qids)
    q = f"""
    SELECT ?person ?personLabel ?start ?end WHERE {{
      VALUES ?pos {{ {values} }}
      ?person wdt:P31 wd:Q5 .
      ?person p:P39 ?posStmt .
      ?posStmt ps:P39 ?pos .
      OPTIONAL {{ ?posStmt pq:P580 ?start. }}
      OPTIONAL {{ ?posStmt pq:P582 ?end.   }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY ?start
    """
    data = wd_sparql(q)
    rows = []
    for b in data["results"]["bindings"]:
        qid   = b["person"]["value"].rsplit("/", 1)[-1]  # e.g., 'Q9682'
        name  = b["personLabel"]["value"]
        start = _norm_year(b.get("start", {}).get("value"))
        end   = _norm_year(b.get("end", {}).get("value"))
        prompt, neg_prompt = person_prompt(name, start)
        rows.append({
            "qid": qid,
            "name": name,
            "start": start,
            "end": end,
            "prompt": prompt,
            "neg_prompt": neg_prompt,
        })
    items = _dedupe_series_rows(rows)
    return {"title": title, "ordered_by":"start", "items": items}



def series_by_award(award_qid: str, title: str, restrict_to_subaward_qids: Optional[List[str]] = None) -> Dict:
    """
    Generic awards (e.g., Nobel Prize winners):
    P166 'award received' with qualifier P585 (point in time).
    If restrict_to_subaward_qids is given (e.g., Physics, Chemistry), we filter the award item.
    """
    base = ensure_qid(award_qid)
    sub_values = ""
    if restrict_to_subaward_qids:
        sub_values = " ".join(f"wd:{ensure_qid(x)}" for x in restrict_to_subaward_qids)
    # If sub_values, accept award = base OR award subclass/instance of any in sub_values, else just base.
    # In practice for Nobels, use the specific subaward QIDs (Physics, Chemistry...) directly.
    filter_clause = f"VALUES ?award {{ {sub_values} }}" if sub_values else f"VALUES ?award {{ wd:{base} }}"
    q = f"""
    SELECT ?person ?personLabel ?when WHERE {{
      {filter_clause}
      ?person wdt:P31 wd:Q5 .
      ?person p:P166 ?stmt .
      ?stmt ps:P166 ?award .
      OPTIONAL {{ ?stmt pq:P585 ?when. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY ?when ?personLabel
    """
    data = wd_sparql(q)
    items = []
    for b in data["results"]["bindings"]:
        name = b["personLabel"]["value"]
        year = _norm_year(b.get("when", {}).get("value"))
        prompt, neg_prompt = person_prompt(name, year)
        items.append({
            "name": name,
            "start": year, "end": "",  # awards are points; put year in 'start'
            "prompt": prompt,
            "neg_prompt": neg_prompt,
        })
    # group by year to get a nice chronological poster
    return {"title": title, "ordered_by": "start", "items": _dedupe_span(items)}

# ---------- PRESET HELPERS (Monarchs, Nobels, CEOs) ----------

# QIDs we’ll use (confirmed on Wikidata pages):
# - monarch of England ..................... Q18810062  :contentReference[oaicite:0]{index=0}
# - monarch of Great Britain ............... Q110324075  :contentReference[oaicite:1]{index=1}
# - monarch of the UK of GB & Ireland ...... Q111722535  :contentReference[oaicite:2]{index=2}
# - monarch of the United Kingdom .......... Q9134365    :contentReference[oaicite:3]{index=3}
def series_monarchs_eng_gb_uk() -> Dict:
    monarch_data = series_by_positions(
        [
            "Q18810062",   # England
            "Q110324075",  # Great Britain
            "Q111722535",  # United Kingdom of Great Britain and Ireland
            "Q9134365",    # United Kingdom
        ],
        title="Monarchs of England, Great Britain & the United Kingdom",
    )
    return monarch_data

def series_potus() -> Dict:
    potus_data = series_by_positions(
        ["Q11696"],
        title="Presidents of the United States",
    )
    for item in potus_data['items']:
        if item['name'] == 'Donald Trump':
            item['prompt'] += ', obese, red necktie'
    return potus_data

# Nobel Prize categories (examples):
#   Physics Q38104, Chemistry Q44585, Medicine Q80061, Literature Q37922, Peace Q35637, Economics Q47528
def series_nobel(category_qid: str, label: str) -> Dict:
    return series_by_award(
        award_qid=category_qid,
        title=f"Nobel Prize in {label} — Laureates",
    )
