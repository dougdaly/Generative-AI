# graphrag/build.py
import networkx as nx
from .rules import parse_policies, extract_policy_id

def add_node(G, label, key, **attrs):
    nid = f"{label}:{key}"
    if nid not in G: G.add_node(nid, label=label, **attrs)
    else:            G.nodes[nid].update(attrs)
    return nid

def add_edge(G, u, etype, v, **attrs):
    G.add_edge(u, v, etype=etype, **attrs)

def add_edge_once(G, u, v, **attrs):
    for _, vv, d in G.out_edges(u, data=True):
        if vv == v and all(d.get(k) == attrs.get(k) for k in attrs):
            return
    G.add_edge(u, v, **attrs)


def build_graph(docs: dict[str,str], icd_rows: list[dict]) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    # Diagnoses
    for r in icd_rows:
        add_node(G, "Diagnosis", r["code"], code=r["code"], name=r["name"])
    for row in icd_rows:  # each is {'code':..., 'name':...}
        code = row["code"]
        name = (row.get("name") or code).strip()
        docs[f"icd:{code}"] = f"ICD-10 {code}: {name}"
    # Known procedures/modifiers
    add_node(G, "Procedure", "PROC-123", code="PROC-123", name="Arthrocentesis")
    add_node(G, "Procedure", "PROC-456", code="PROC-456", name="Nerve conduction study")
    add_node(G, "Modifier",  "50",      code="50",      name="Bilateral")

    for doc_id, text in docs.items():
        pid = extract_policy_id(text) or doc_id
        cov = add_node(G, "Coverage", pid, policy=pid, payer="CMS")
        for spec in parse_policies(text):
            px = add_node(G, "Procedure", spec.proc_code, code=spec.proc_code)
            add_edge(G, px, "COVERED_BY", cov)
            if spec.indicated_dx:
                dx = add_node(G, "Diagnosis", spec.indicated_dx, code=spec.indicated_dx)
                add_edge(G, px, "INDICATED_FOR", dx)
            if spec.requires_modifier:
                code, cond = spec.requires_modifier
                mod = add_node(G, "Modifier", code, code=code)
                add_edge(G, px, "REQUIRES_MODIFIER", mod, condition=cond)
            if spec.rule_text:
                rule = add_node(G, "Rule", spec.proc_code+"_rule", text=spec.rule_text)
                add_edge(G, cov, "JUSTIFIED_BY", rule)
    return G

def attach_is_a(G, specific: str, general: str):
    s = f"Diagnosis:{specific}"; 
    g = f"Diagnosis:{general}"
    if s in G and g in G: 
        add_edge_once(G, s, g, "IS_A")
