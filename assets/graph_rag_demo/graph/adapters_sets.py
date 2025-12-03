def add_edge_once(G, u, v, **attrs):
    for _, vv, dd in G.out_edges(u, data=True):
        if vv == v and all(dd.get(k) == attrs.get(k) for k in attrs):
            return
    G.add_edge(u, v, **attrs)

def _icd_prefix(pattern: str) -> str:
    # "M75.0x" -> "M750"
    return pattern.upper().replace(".", "").rstrip("X*")

def add_sets_and_policies(eng, yaml_data: dict):
    G = eng.G
    nid = eng._nid

    # ---- 1) Build set nodes and an in-memory index for membership checks ----
    eng._sets_index = {}  # id -> dict(kind=..., params...)
    for s in yaml_data.get("sets", []):
        sid = s["id"]
        kind = s["kind"]
        rec = {"kind": kind}
        if kind == "cpt_range":
            rec["start"] = int(s["start"])
            rec["end"]   = int(s["end"])
        elif kind in ("proc_list", "dx_list"):
            rec["members"] = set(s.get("members", []))
        elif kind == "icd_family":
            rec["pattern"] = s["pattern"]
            rec["prefix"]  = _icd_prefix(s["pattern"])
        else:
            continue

        eng._sets_index[sid] = rec
        # Add set nodes (for explainable paths)
        if kind.startswith("cpt") or kind == "proc_list":
            G.add_node(
                eng._nid("ProcSet", sid),
                label="ProcSet",
                set_id=sid,
                code=sid,          
                kind=kind,
                name=sid
            )
        else:
            G.add_node(
                eng._nid("DxSet", sid),
                label="DxSet",
                set_id=sid,
                code=sid,          
                kind=kind,
                name=sid
    )
    # ---- 2) Build policy nodes and connect to the sets they use ----
    eng._policies = []  # cache raw policy records if needed
    for p in yaml_data.get("policies", []):
        pol_id = p["policy"]
        cov = nid("Coverage", pol_id)
        if cov not in G:
            G.add_node(cov, label="Coverage",
                       policy=pol_id,
                       payer=p.get("payer",""),
                       name=p.get("title") or pol_id)

        for sid in p.get("proc_sets", []):
            add_edge_once(G, eng._nid("Coverage", pol_id), eng._nid("ProcSet", sid), etype="USES_PROCSET")
        for sid in p.get("dx_sets", []):
            add_edge_once(G, eng._nid("Coverage", pol_id), eng._nid("DxSet",   sid), etype="USES_DXSET")

        # docs for citations
        eng.doc_by_node.setdefault(cov, []).append({
            "doc_id": pol_id,
            "text_short": p.get("title") or "Coverage policy"
        })
        eng._policies.append(p)

    # tiny cache for membership results
    eng._membership_cache = {}  # (code, sid) -> bool
