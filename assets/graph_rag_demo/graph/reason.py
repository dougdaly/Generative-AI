import re

ICD_RE = re.compile(r"\b([A-Z][0-9][0-9]\.[0-9A-Z]{0,2})\b", re.I)

def expand_subgraph(G, seeds, depth=2):
    seen_nodes = set(seeds)
    frontier = list(seeds)
    for _ in range(depth):
        nxt = set()
        for u in frontier:
            nxt.update(G.successors(u))
            nxt.update(G.predecessors(u))
        frontier = [n for n in nxt if n not in seen_nodes]
        seen_nodes.update(frontier)
    return G.subgraph(seen_nodes).copy()

def relevant_edges(SG, seeds):
    """Keep edges that explain coverage: direct links, set links, modifiers, rules, plus seed IS_A chain."""
    seed_set = set(seeds)
    ALLOW = {
        "INDICATED_FOR", "COVERED_BY", "COVERED_FOR", "COVERS",
        "QUALIFIES_FOR", "REQUIRES_DIAGNOSIS",
        "JUSTIFIED_BY", "REQUIRES_MODIFIER",
        "IS_A", "IS_IN", "USES_PROCSET", "USES_DXSET",
    }
    keep = []
    for u, v, data in SG.edges(data=True):
        et = data.get("etype")
        if et not in ALLOW:
            continue
        # Keep IS_A only if it touches any seed (tighten chain)
        if et == "IS_A" and (u not in seed_set and v not in seed_set):
            continue
        keep.append((u, et, v))
    # de-dupe while preserving order
    seen, out = set(), []
    for e in keep:
        if e not in seen:
            out.append(e); seen.add(e)
    return out

def doc_title_and_url(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0] if lines else "Document"
    url   = next((ln.replace("Source:","").strip() for ln in lines if ln.startswith("Source:")), "")
    return title, url

def first_edge_attrs(G, u, v):
    data = G.get_edge_data(u, v)
    if data is None: return {}
    if isinstance(data, dict) and data and isinstance(next(iter(data.values())), dict):
        return next(iter(data.values()))   # MultiDiGraph
    return data                             # DiGraph

import re
from collections import defaultdict

ICD_RE = re.compile(r'[A-TV-Z]\d[\dA-Z](?:\.?\d[\dA-Z]*)?')

def analyze(SG, seed_nodes, focus_procs=None):
    """
    Compute coverage by intersecting:
      (seeds' ProcSet memberships)  ∩  (policy USES_PROCSET)
      AND
      (seeds' DxSet memberships)    ∩  (policy USES_DXSET)

    Also collect modifiers, rules/exceptions, and a clean reason-path.
    """
    # Snapshot labels for quick checks
    label_of = {n: SG.nodes[n].get("label") for n in SG.nodes}

    # Build adjacency (typed)
    out = defaultdict(list); inc = defaultdict(list)
    for u, v, d in SG.edges(data=True):
        et = d.get("etype")
        out[u].append((et, v))
        inc[v].append((et, u))

    # Seeds partition
    seeds = list(seed_nodes)
    seed_dx    = [n for n in seeds if label_of.get(n) == "Diagnosis"]
    seed_procs_all = [n for n in seeds if label_of.get(n) == "Procedure"]
    seed_procs = [n for n in seed_procs_all if not focus_procs or n in focus_procs]

    PS_from_seeds = set()
    for p in seed_procs:
        for et, v in out[p]:
            if et == "IS_IN" and label_of.get(v) == "ProcSet":
                PS_from_seeds.add(v)
        for et, u in inc[p]:
            if et in ("IS_IN","HAS_MEMBER") and label_of.get(u) == "ProcSet":
                PS_from_seeds.add(u)
        # Collect seeds' set memberships
        PS_from_seeds, DS_from_seeds = set(), set()
        for p in seed_procs:
            for et, v in out[p]:
                if et == "IS_IN" and label_of.get(v) == "ProcSet":
                    PS_from_seeds.add(v)
            for et, u in inc[p]:
                if et in ("IS_IN","HAS_MEMBER") and label_of.get(u) == "ProcSet":
                    PS_from_seeds.add(u)

    # Allow roll-up DX or specifics to count
    for dnode in seed_dx:
        for et, v in out[dnode]:
            if et == "IS_IN" and label_of.get(v) == "DxSet":
                DS_from_seeds.add(v)
        for et, u in inc[dnode]:
            if et in ("IS_IN","HAS_MEMBER") and label_of.get(u) == "DxSet":
                DS_from_seeds.add(u)

    # Map each policy to the sets it uses
    cov_nodes = [n for n in SG.nodes if label_of.get(n) in ("Coverage","Policy")]
    COV_to_PS, COV_to_DS = defaultdict(set), defaultdict(set)
    for cov in cov_nodes:
        for et, v in out[cov]:
            if et == "USES_PROCSET" and label_of.get(v) == "ProcSet":
                COV_to_PS[cov].add(v)
            if et == "USES_DXSET" and label_of.get(v) == "DxSet":
                COV_to_DS[cov].add(v)
        for et, u in inc[cov]:
            if et == "USES_PROCSET" and label_of.get(u) == "ProcSet":
                COV_to_PS[cov].add(u)
            if et == "USES_DXSET" and label_of.get(u) == "DxSet":
                COV_to_DS[cov].add(u)

    # Compute covered policies: intersection on both axes
    covered_policies = [
        cov for cov in cov_nodes
        if (COV_to_PS[cov] & PS_from_seeds) and (COV_to_DS[cov] & DS_from_seeds)
    ]
    # Edge list to render (keep what explains coverage)
    ALLOW = {
        "INDICATED_FOR","COVERED_BY","COVERED_FOR","COVERS",
        "QUALIFIES_FOR","REQUIRES_DIAGNOSIS",
        "JUSTIFIED_BY","REQUIRES_MODIFIER",
        "IS_A","IS_IN","USES_PROCSET","USES_DXSET",
    }
    seed_set = set(seeds)
    edges = []
    seen = set()
    for u, v, d in SG.edges(data=True):
        et = d.get("etype")
        if et not in ALLOW: 
            continue
        if et == "IS_A" and u not in seed_set and v not in seed_set:
            continue
        tup = (u, et, v)
        if tup not in seen:
            edges.append(tup); seen.add(tup)

    # Node/edge attrs snapshot for renderer
    nodes_attrs = {}
    for u,_,v in edges:
        if u not in nodes_attrs: nodes_attrs[u] = dict(SG.nodes[u])
        if v not in nodes_attrs: nodes_attrs[v] = dict(SG.nodes[v])
    edge_attrs = {(u,v): SG.get_edge_data(u,v)[min(SG.get_edge_data(u,v))]  # first multiedge
                  if isinstance(SG.get_edge_data(u,v), dict) else {} for (u,_,v) in edges}

    # Modifiers
    modifiers, seen_mods = [], set()
    for u, et, v in edges:
        if et == "REQUIRES_MODIFIER" and label_of.get(v) == "Modifier":
            attrs = edge_attrs.get((u, v), {})
            key = (SG.nodes[v].get("code"), attrs.get("condition",""))
            if key not in seen_mods:
                seen_mods.add(key)
                modifiers.append({"code": key[0], "condition": key[1]})

    # Rules / exceptions
    rules, exceptions = [], []
    for u, et, v in edges:
        if et == "JUSTIFIED_BY" and label_of.get(v) == "Rule":
            txt = SG.nodes[v].get("text","")
            if txt:
                rules.append(txt)
                if "unless" in txt.lower():
                    for c in ICD_RE.findall(txt):
                        exceptions.append({"type":"auth_waiver", "icd": c.upper()})

    # Per-DX qualifying map (policy-aware) for rendering clarity
    dx_sets_any_by_code  = defaultdict(set)
    dx_sets_qual_by_code = defaultdict(set)
    dx_qual_policies     = defaultdict(set)

    # Build dictionaries from the graph we already have
    # (This assumes you materialized IS_IN for each dx code considered)
    for dnode in seed_dx:
        dcode = SG.nodes[dnode].get("code") or dnode
        for et, ds in out[dnode]:
            if et == "IS_IN" and label_of.get(ds) == "DxSet":
                dx_sets_any_by_code[dcode].add(SG.nodes[ds].get("code") or SG.nodes[ds].get("set_id") or ds)

    # Qualifying only if some policy intersects on both axes and uses that DxSet
    for cov in covered_policies:
        for ds in COV_to_DS[cov] & DS_from_seeds:
            # Which dx codes lead to this ds?
            for dnode in seed_dx:
                if any(et == "IS_IN" and tgt == ds for et, tgt in out[dnode]):
                    dcode = SG.nodes[dnode].get("code") or dnode
                    dx_sets_qual_by_code[dcode].add(SG.nodes[ds].get("code") or SG.nodes[ds].get("set_id") or ds)
                    polid = SG.nodes[cov].get("policy") or cov
                    dx_qual_policies[dcode].add(polid)

    # Ensure every DX shows up in the per-DX maps
    for dnode in seed_dx:
        dcode = SG.nodes[dnode].get("code") or dnode
        dx_sets_any_by_code.setdefault(dcode, set())
        dx_sets_qual_by_code.setdefault(dcode, set())
        dx_qual_policies.setdefault(dcode, set())

    return {
        "covered": bool(covered_policies),
        "policies": covered_policies,
        "modifiers": modifiers,
        "rules": rules,
        "exceptions": exceptions,
        "seeds": list(seeds),
        "edges": edges,
        "nodes": nodes_attrs if nodes_attrs else {n: dict(SG.nodes[n]) for n in SG.nodes},
        "edge_attrs": edge_attrs,
        "cit_nodes": set(nodes_attrs.keys()),
        "nodes_seen": list(nodes_attrs.keys()),
        # extra maps for renderer
        "dx_sets_any_by_code":  {k: sorted(v) for k,v in dx_sets_any_by_code.items()},
        "dx_sets_qual_by_code": {k: sorted(v) for k,v in dx_sets_qual_by_code.items()},
        "dx_qual_policies":     {k: sorted(v) for k,v in dx_qual_policies.items()},
    }
