
def render_answer(facts: dict, doc_by_node: dict[str, list], SG=None) -> str:
    # derive grounded ICDs from seeds
    grounded_icds = [
        n.split("DX:", 1)[1]
        for n in facts.get("seeds", [])
        if isinstance(n, str) and n.startswith("DX:")
    ]

    lines = []

    # Verdict
    if facts.get("covered"):
        waived = [e for e in facts.get("exceptions", [])
                  if e.get("type") == "auth_waiver"
                  and any(e.get("icd","").upper().startswith(g.upper()) for g in grounded_icds)]
        if waived:
            which = ", ".join(sorted({e["icd"] for e in waived}))
            lines.append(f"A: Yes — prior auth is waived when {which} is documented (per policy).")
        else:
            lines.append("A: Yes — covered when medically necessary for the indicated diagnosis.")
    else:
        lines.append("A: Coverage not found for this pairing in the local graph.")

    # Multiple diagnoses
    dx_any  = facts.get("dx_sets_any_by_code", {})
    dx_qual = facts.get("dx_sets_qual_by_code", {})
    dx_pols = facts.get("dx_qual_policies", {})

    if dx_any and len(dx_any) > 1:
        lines.append("\nPer-diagnosis:")
        for dxc in sorted(dx_any.keys()):
            qual_sets = dx_qual.get(dxc, [])
            if qual_sets:
                pols = dx_pols.get(dxc, [])
                pol_str = f" under {', '.join(pols)}" if pols else ""
                lines.append(f"  {dxc}: ✓ qualifies{pol_str} via DxSet[{', '.join(qual_sets)}]")
            else:
                # Either it matched some DxSet but no policy with this proc, or no DxSet at all
                any_sets = dx_any.get(dxc, [])
                if any_sets:
                    lines.append(f"  {dxc}: ✗ matches DxSet[{', '.join(any_sets)}] but not with this procedure")
                else:
                    lines.append(f"  {dxc}: ✗ no matching policy set")


    # Modifiers
    for m in facts.get("modifiers", []):
        note = f"Note: Append modifier -{m.get('code','')}" + (f" ({m.get('condition')})" if m.get("condition") else "")
        lines.append(note)

    # Reason path
    if facts.get("edges"):
        lines.append("\nWhy (reason path):")
        for u, et, v in facts["edges"]:
            uL = facts["nodes"][u].get("label", "")
            uK = facts["nodes"][u].get("code") or facts["nodes"][u].get("policy", "")
            vL = facts["nodes"][v].get("label", "")
            vK = facts["nodes"][v].get("code") or facts["nodes"][v].get("policy", "")
            cond = facts.get("edge_attrs", {}).get((u, v), {}).get("condition", "")
            lines.append(f"  {uL}:{uK} --{et}{(' ('+cond+')') if cond else ''}→ {vL}:{vK}")

    # Matched sets
    ms = facts.get("matched_sets_by_policy", {})
    if ms:
        lines.append("\nMatched sets:")
        for pol in facts.get("policies", []):
            proc_sets = ", ".join(sorted(ms.get(pol, {}).get("proc", []))) or "—"
            dx_sets   = ", ".join(sorted(ms.get(pol, {}).get("dx", [])))   or "—"
            pol_name  = facts["nodes"].get(pol, {}).get("policy") or facts["nodes"].get(pol, {}).get("name") or pol
            lines.append(f"  {pol_name}: ProcSet[{proc_sets}] & DxSet[{dx_sets}]")

    # ---- Citations (robust) ----
    def normalize_doc_item(x):
        # Accept dict, tuple, or string; return (doc_id, text_short)
        if isinstance(x, dict):
            return (x.get("doc_id", ""), x.get("text_short", x.get("text","")))
        if isinstance(x, tuple) and len(x) >= 2:
            return (x[0], x[1])
        if isinstance(x, str):
            return ("", x)
        return ("", "")

    # pick targets to cite
    nodes_seen = list(facts.get("nodes_seen", []))
    if not nodes_seen:
        # backfill with anything we actually referenced
        nodes_seen = list(facts.get("nodes", {}).keys()) or list(facts.get("seeds", []))

    citations_set = set()

    def collect_docs_for(nid, budget=2):
        items = doc_by_node.get(nid, []) or []
        out = []
        for it in items:
            did, txt = normalize_doc_item(it)
            if txt:
                out.append((did, txt))
            if len(out) >= budget:
                break
        return out

    # 1) direct docs
    for nid in nodes_seen:
        for item in collect_docs_for(nid, budget=2):
            citations_set.add(item)

    # 2) neighbor fallback via SG (parents/children one hop)
    if SG is not None:
        for nid in nodes_seen:
            if nid in SG:
                # predecessors and successors
                for nb in list(SG.predecessors(nid)) + list(SG.successors(nid)):
                    for item in collect_docs_for(nb, budget=1):
                        citations_set.add(item)

    # 3) same-code fallback within the facts graph
    code_index = {}
    for nid, attrs in facts.get("nodes", {}).items():
        code = attrs.get("code")
        if code:
            code_index.setdefault(code, []).append(nid)

    for nid in nodes_seen:
        code = facts.get("nodes", {}).get(nid, {}).get("code")
        if code:
            for alt in code_index.get(code, []):
                for item in collect_docs_for(alt, budget=1):
                    citations_set.add(item)

    # 4) seeds fallback
    for nid in facts.get("seeds", []):
        for item in collect_docs_for(nid, budget=1):
            citations_set.add(item)

    # format
    lines.append("\nCitations:")
    if citations_set:
        # stable order, cap total
        for did, txt in list(sorted(citations_set))[:8]:
            if did:
                lines.append(f"- {did}: {txt}")
            else:
                lines.append(f"- {txt}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)
