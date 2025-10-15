# registry.py
from __future__ import annotations
from pathlib import Path
import csv, yaml, networkx as nx
from collections import defaultdict
import re, textwrap
import pandas as pd

SHORT = {
    "Diagnosis": "DX", "Procedure": "PX", "Modifier": "MD", "Coverage": "COV",
    "ProcSet": "PS", "DxSet": "DS"
}


def _load_csv_records(path: Path, fields: list[str]) -> list[dict]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8", sep='|')
    if fields: df = df[fields]
    df = df.apply(lambda s: s.str.strip())
    df = df.loc[(df != "").all(axis=1)].drop_duplicates()
    return df.to_dict("records")

def _load_yaml_records(path: Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    out = []
    for row in data:
        if isinstance(row, dict):
            out.append({str(k).strip(): str(v).strip() if isinstance(v, str) else v
                        for k,v in row.items() if k is not None and str(k).strip() != ""})
    return out

def make_id(template: str, row: dict) -> str:
    return template.format(**row)


def load_yaml(p: Path): 
    with open(p, "r", encoding="utf-8") as f: 
        return yaml.safe_load(f)

def load_csv_rows(p: Path):
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter='|'):
            yield {k: (v.strip() if isinstance(v,str) else v) for k,v in row.items()}

def _load_text_file(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def _load_docs(cfg_docs: list[dict]) -> dict[str, str]:
    out = {}
    for block in cfg_docs or []:
        kind = block.get("kind")
        if kind == "dir":
            root = Path(block["path"])
            for ext in ("*.txt","*.md"):
                for path in root.rglob(ext):
                    doc_id = path.stem  # e.g. cms_arthrocentesis
                    out[doc_id] = _load_text_file(path)
        elif kind == "file":
            path = Path(block["path"])
            doc_id = block.get("id") or path.stem
            out[doc_id] = _load_text_file(path)
        else:
            raise ValueError(f"Unknown docs.kind={kind}")
    return out

# finds matching item within a graph
def _lookup(G: nx.MultiDiGraph, label: str, code: str) -> str | None:
    for n, d in G.nodes(data=True):
        if d.get("label")==label and (d.get("code")==code or d.get("policy")==code or d.get("id")==code):
            return n
    return None

# For flexibility -- allow edge to be one of code, policy or id.
def _pick_key(d: dict) -> str:
    for k in ("code", "policy", "id"):
        if k in d:
            return k
    raise KeyError("edge endpoint must include one of: code|policy|id")


def _normalize_name(n: str | None) -> list[str]:
    if not n:
        return []
    s = n.strip().lower()
    # add a few simple variants – you can extend if needed
    return [s, s.replace("/", " "), s.replace("-", " ")]

def _code_variants(code: str, label: str) -> list[str]:
    out = []
    if not code:
        return out
    out.append(code)                           # e.g., M75.01 or M75.0x
    out.append(code.replace(".", ""))          # M7501
    out.append(f"{SHORT.get(label, label[:3].upper())}:{code}")    # DX:M75.01
    # wildcard M75.0x → regex pattern for any digit
    if code.endswith("x") or code.endswith("X"):
        # turn M75.0x into \bM75\.0\d\b
        patt = re.escape(code[:-1]).replace(r"\.", r"\.") + r"\d"
        out.append(f"REGEX::{patt}")
    return out

def _compile_patterns(keys: set[str]) -> list[re.Pattern]:
    pats = []
    for k in keys:
        if k.startswith("REGEX::"):
            patt = k.split("::", 1)[1]
            pats.append(re.compile(patt, flags=re.IGNORECASE))
            continue
        # Looser for codes (digits/dots), strict word-boundary for plain words
        if any(ch.isdigit() for ch in k) or "." in k:
            patt = re.escape(k)
            pats.append(re.compile(patt, flags=re.IGNORECASE))
        else:
            pats.append(re.compile(rf"\b{re.escape(k)}\b", flags=re.IGNORECASE))
    return pats

def match_keys_for_node(node_attrs: dict, synonyms: list[tuple[str,str,str]]) -> set[str]:
    """keys = code variants + normalized official name + synonyms for (label,code)."""
    label = node_attrs.get("label","")
    code  = node_attrs.get("code","")
    name  = node_attrs.get("name","") or ""
    keys = set()

    # your existing helpers
    keys |= set(_code_variants(code, label))
    keys |= set(_normalize_name(name))

    # NEW: add synonyms for this exact (label, code)
    syn_terms = [term for (term, lab, cod) in synonyms if lab == label and cod == code]
    keys |= {t.strip().lower() for t in syn_terms if t}

    return keys


def build_doc_index(G, docs: dict[str,str], synonyms: list[tuple[str,str,str]]) -> dict:
    doc_by_node: dict[str, list[tuple[str, str]]] = {}
    def _add_cite(nid, doc_id, snippet):
        doc_by_node.setdefault(nid, []).append((doc_id, snippet))
    # Pre-lower docs once
    lowered = {doc_id: txt.lower() for doc_id, txt in docs.items()}
    for nid, attrs in G.nodes(data=True):
        if attrs.get("label") == "Diagnosis" and nid not in doc_by_node:
            code = attrs.get("code", "")
            name = attrs.get("name", "").strip() or code
            _add_cite(nid, "icd10", f"{code} — {name}")
        keys = match_keys_for_node(attrs, synonyms)
        if not keys:
            continue
        pats = _compile_patterns(keys)
        hits = []
        for doc_id, low in lowered.items():
            if any(p.search(low) for p in pats):
                # store (doc_id, short snippet or title)
                snippet = (docs[doc_id][:200] + "…") if len(docs[doc_id]) > 200 else docs[doc_id]
                hits.append((doc_id, snippet))
        if hits:
            doc_by_node[nid] = hits
    return doc_by_node

def build_doc_by_node(G, docs: dict[str, str], syn_list: list[tuple[str,str,str]]):
    # invert synonyms: (label, code) -> terms
    syn = defaultdict(set)
    for term, label, code in syn_list or []:
        if term and label and code:
            syn[(label, code)].add(term.strip().lower())

    # pre-lower docs for matching (keep original for snippets)
    docs_lower = {doc_id: txt.lower() for doc_id, txt in docs.items()}

    out = defaultdict(list)

    for nid, nd in G.nodes(data=True):
        label = nd.get("label")
        code  = nd.get("code")
        name  = nd.get("name")  # ICD name for diagnoses

        if not (label and code):
            continue

        keys = set()
        # synonyms
        keys |= syn.get((label, code), set())
        # code variants
        for s in _code_variants(code, label):
            keys.add(s.lower())
        # name variants (esp. DX names)
        for s in _normalize_name(name):
            keys.add(s)

        if not keys:
            continue

        patterns = _compile_patterns(keys)

        for doc_id, low in docs_lower.items():
            if any(p.search(low) for p in patterns):
                out[nid].append({
                    "doc_id": doc_id,
                    "text_short": textwrap.shorten(docs[doc_id], width=200, placeholder="…"),
                })

    return dict(out)

def build_graph_from_registry(cfg_path: Path):
    """
    Returns:
      G    : networkx.MultiDiGraph with nodes/edges
      syn  : list[(term,label,code)] synonyms
      cfg  : parsed registry dict
      docs : dict[doc_id -> full_text]
    """
    base = Path(cfg_path).parent
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    G = nx.MultiDiGraph()

    # ---- Nodes ----
    for label, spec in cfg.get("nodes", {}).items():
        src = spec["source"]
        kind = src["kind"]
        if kind == "csv":
            rows = _load_csv_records(Path(cfg_path).parent / src["path"], spec.get("fields", []))
        elif kind == "yaml":
            rows = _load_yaml_records(Path(cfg_path).parent / src["path"])
        else:
            raise ValueError(f"Unsupported source kind: {kind}")

        id_tmpl = src["id_template"]
        for row in rows:
            node_id = make_id(id_tmpl, row)
            attrs = {"label": label, **row}
            # sanitize keys
            clean = {str(k).strip(): v for k,v in attrs.items() if k is not None and str(k).strip() != ""}
            G.add_node(str(node_id), **clean)

    # Edges 
    for es in cfg.get("edges", []):
        path = base / es["path"]
        if es["kind"] == "csv":
            for row in load_csv_rows(path):
                u = _lookup(G, row["src_label"], row["src_code"])
                v = _lookup(G, row["dst_label"], row["dst_code"])
                if u and v:
                    attrs = {}
                    if "condition" in row and row["condition"]:
                        attrs["condition"] = row["condition"]
                    G.add_edge(u, v, etype=row["etype"], **attrs)
        elif es["kind"] == "yaml":
            data = load_yaml(path)
            for e in data.get("edges", []):
                src_key = _pick_key(e["src"])
                dst_key = _pick_key(e["dst"])
                u = _lookup(G, e["src"]["label"], e["src"][src_key])
                v = _lookup(G, e["dst"]["label"], e["dst"][dst_key])
                if u and v:
                    attrs = {k: v for k, v in e.items() if k not in ("src", "dst", "etype")}
                    G.add_edge(u, v, etype=e["etype"], **attrs)
        else:
            raise ValueError(f"Unknown edge source kind: {es['kind']}")

    # 3) Synonyms
    syn_spec = cfg.get("synonyms")
    synonyms = []
    if syn_spec:
        spath = base / syn_spec["path"]
        for row in load_csv_rows(spath):
            synonyms.append((row["term"].strip().lower(), row["label"], row["code"]))
    # 4) docs
    docs = _load_docs(cfg.get("docs", []))
    doc_by_node = build_doc_index(G, docs, synonyms)
    return G, synonyms, cfg, doc_by_node, docs

