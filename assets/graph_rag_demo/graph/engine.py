# engine.py
from __future__ import annotations
from pathlib import Path
import networkx as nx
from .registry import build_graph_from_registry, SHORT
from .ground import ground
from .reason import expand_subgraph, analyze
from .render import render_answer
import re
from collections import defaultdict

CPT5 = re.compile(r"^\d{5}$")
PROC_CANON = {"PROC-123": "20610"}  # collapse demo alias → real CPT (add more if you have them)
ICD_RE = re.compile(r'\b[A-TV-Z]\d[\dA-Z](?:\.?\d[\dA-Z]*)?\b')   # e.g. M75.41, M75.0x, E11.40
CPT_RE = re.compile(r'\b\d{5}\b')                                 # 5-digit CPT like 20610


def _canon_proc(code: str) -> str:
    return PROC_CANON.get(code, code)

def _prefer_cpt(proc_codes: set[str]) -> set[str]:
    cpts = {c for c in proc_codes if CPT5.match(c)}
    return cpts or proc_codes


def add_edge_once(G, u, v, **attrs):
    for _, vv, dd in G.out_edges(u, data=True):
        if vv == v and all(dd.get(k) == attrs.get(k) for k in attrs):
            return
    G.add_edge(u, v, **attrs)


def _norm_icd(s: str) -> str:
    return s.upper().strip()

def _norm_cpt(s: str) -> str:
    return s.strip()

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
        dxs.add(_norm_icd(tok))
    for tok in CPT_RE.findall(query):
        procs.add(_norm_cpt(tok))

    # 2) Ensure codes exist as strings (your _iter_grounded handles strings fine)
    #    Keep both specifics (M75.41) and families (M75.0x) if present.
    #    No dedup needed beyond set().

    return {"procedures": procs, "diagnoses": dxs, "modifiers": mods}

def _norm_icd(s: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper())

def _icd_prefix(pattern: str) -> str:
    p = (pattern or '').upper().replace('.', '')
    return p[:-1] if p.endswith(('X','*')) else p


def _iter_grounded(raw):
    """
    Yield (label, code) from ground() output.
    Accept strings, sets, lists, tuples, dicts.
    Preserve the label implied by the top-level key.
    """
    if not raw:
        return

    key2label = {
        "procedures": "Procedure",
        "diagnoses":  "Diagnosis",
        "modifiers":  "Modifier",
        "coverage":   "Coverage",
    }

    def emit(items, default_label):
        if items is None:
            return
        if isinstance(items, dict):
            lbl = items.get("label") or default_label
            code = items.get("code")
            if lbl and code:
                yield lbl, code
            return
        # normalize to iterable
        if isinstance(items, (set, list, tuple)):
            iterable = items
        else:
            iterable = [items]

        for it in iterable:
            if isinstance(it, tuple):
                if len(it) == 3:
                    _, lbl, code = it
                elif len(it) == 2:
                    lbl, code = it
                else:
                    continue
                yield lbl, code
            elif isinstance(it, dict):
                lbl = it.get("label") or default_label
                code = it.get("code")
                if lbl and code:
                    yield lbl, code
            elif isinstance(it, str):
                s = it.strip()
                if ":" in s:
                    lbl, code = s.split(":", 1)
                    yield lbl, code
                else:
                    # key controls the label — no cross-label spray
                    yield default_label, s

    for k, items in raw.items():
        lbl = key2label.get(k)
        if not lbl:
            continue
        for pair in emit(items, lbl):
            yield pair


def norm_code(code: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', (code or '').upper())

def parse_wildcard(code: str) -> str | None:
    """
    Return normalized prefix if code represents a wildcard.
    Examples:
      'M75.0x' -> 'M750'
      'M750*'  -> 'M750'
    """
    if not code:
        return None
    c = code.upper().replace('.', '')
    if c.endswith('X') or c.endswith('*'):
        return c[:-1]
    return None

def build_norm_index(G: nx.MultiDiGraph) -> dict[tuple[str,str], str]:
    """Map (label, normalized_code) -> node_id for fast lookups."""
    idx = {}
    for nid, at in G.nodes(data=True):
        lbl, code = at.get('label'), at.get('code')
        if lbl and code:
            idx[(lbl, norm_code(code))] = nid
    return idx

class GraphRAG:
    def __init__(self, registry_yaml: Path):
        self.G, self.syn, self.cfg, self.doc_by_node, self.docs = build_graph_from_registry(registry_yaml)
        REG_SHORT = {lbl: spec.get("short") for lbl, spec in self.cfg["nodes"].items()}
        self._short_map = REG_SHORT.copy()
        self._short_map.update({k: v for k, v in SHORT.items() if k not in self._short_map})
        self.norm_index = build_norm_index(self.G)
        # Prefer shorts from the registry; fall back to your SHORT dict; then to label[:2]
        self.short = {lbl: spec.get("short")
                    for lbl, spec in self.cfg["nodes"].items()}
        self.short_fallback = SHORT  # your constant {"Diagnosis":"DX", "Procedure":"PX", "Modifier":"MD", "Coverage":"COV"}

    def _short(self, label: str) -> str:
        return self._short_map.get(label, label[:2].upper())    
        # Identify procedure
    def _proc_in_set(self, code: str, sid: str) -> bool:
        spec = self._get_set_spec(sid)
        if not spec:
            return False
        kind = spec.get('kind')

        if kind == 'proc_list':
            members_norm = spec.get('members_norm')
            if isinstance(members_norm, set):
                return str(code) in members_norm
            members = spec.get('members') or []
            return str(code) in {str(x) for x in members}

        if kind == 'cpt_range':
            try:
                c = int(code)
                start = int(spec.get('start'))
                end   = int(spec.get('end'))
            except Exception:
                return False
            return start <= c <= end

        return False
        # Identify diagnosis
    def _get_set_spec(self, sid: str) -> dict | None:
        idx = getattr(self, '_sets_index', None)
        if not isinstance(idx, dict):
            return None
        # common layouts:
        # 1) {"icd:rotator_cuff": {...}, "cpt:joint_injection": {...}}
        if sid in idx and isinstance(idx[sid], dict) and 'kind' in idx[sid]:
            return idx[sid]
        # 2) {"by_id": {"icd:rotator_cuff": {...}, ...}, ...}
        by_id = idx.get('by_id')
        if isinstance(by_id, dict) and sid in by_id:
            return by_id[sid]
        return None

    def _dx_in_set(self, code: str, sid: str) -> bool:
        spec = self._get_set_spec(sid)
        if not spec:
            return False
        kind = spec.get('kind')

        if kind == 'icd_family':
            pref = _icd_prefix(spec.get('pattern', ''))
            return bool(pref) and _norm_icd(code).startswith(pref)

        if kind == 'dx_list':
            # Prefer a pre-normalized membership set if your index provides it
            members_norm = spec.get('members_norm')
            if isinstance(members_norm, set):
                return _norm_icd(code) in members_norm
            # Fallback: normalize on the fly
            members = spec.get('members') or []
            return _norm_icd(code) in {_norm_icd(x) for x in members}

        if kind == 'icd_range':
            start = _norm_icd(spec.get('start', ''))
            end   = _norm_icd(spec.get('end', ''))
            c     = _norm_icd(code)
            return len(c) == len(start) == len(end) and start <= c <= end

        return False


    def _nid(self, label: str, code: str) -> str:
        return f"{self._short(label)}:{code}"

    def ensure_rollup_node(self, label: str, prefix: str) -> str:
        roll_code = f"{prefix}*"
        roll_id = self._nid(label, roll_code)

        if roll_id not in self.G:
            self.G.add_node(roll_id, label=label, code=roll_code,
                            name=f"{label} roll-up {roll_code}", rollup=True)
            self._index_put(label, roll_code, roll_id)

        # Attach children from SAME label; no self; no duplicate edges
        for nid, at in self.G.nodes(data=True):
            if at.get('label') != label: 
                continue
            if nid == roll_id or at.get('rollup'):
                continue
            c = at.get('code')
            if c and norm_code(c).startswith(prefix):
                if not any(v == roll_id and d.get('etype') == 'IS_A'
                        for _, v, d in self.G.out_edges(nid, data=True)):
                    self.G.add_edge(nid, roll_id, etype="IS_A")

        # optional but recommended: propagate child docs up so roll-ups can cite
        self._propagate_docs_to_rollup(roll_id)
        return roll_id

    def is_a(self, specific_code: str, rollup_code: str):
        u = self._by_code("Diagnosis", specific_code) or self._nid("Diagnosis", specific_code)
        v = self._by_code("Diagnosis", rollup_code)  or self._nid("Diagnosis", rollup_code)
        if u not in self.G:
            self.G.add_node(u, label="Diagnosis", code=specific_code, name=specific_code)
            self._index_put("Diagnosis", specific_code, u)
        if v not in self.G:
            self.G.add_node(v, label="Diagnosis", code=rollup_code, name=rollup_code)
            self._index_put("Diagnosis", rollup_code, v)
        if not any(x == v and d.get('etype') == 'IS_A' for _, x, d in self.G.out_edges(u, data=True)):
            self.G.add_edge(u, v, etype="IS_A")

    def _by_code(self, label: str, code: str) -> str | None:
        # exact attr match
        for nid, at in self.G.nodes(data=True):
            if at.get('label') == label and at.get('code') == code:
                return nid
        # normalized index
        nid = self.norm_index.get((label, norm_code(code)))
        if nid:
            return nid
        # wildcard → create roll-up
        prefix = parse_wildcard(code)
        if prefix:
            return self.ensure_rollup_node(label, prefix)
        return None

    def _index_put(self, label: str, code: str, nid: str):
        self.norm_index[(label, norm_code(code))] = nid

    def _propagate_docs_to_rollup(self, roll_id: str, max_docs: int = 5):
        docs = []
        for u, v, d in self.G.in_edges(roll_id, data=True):
            if d.get('etype') == 'IS_A':
                docs.extend(self.doc_by_node.get(u, []))
        if docs:
            uniq, seen = [], set()
            for x in docs:
                if x not in seen:
                    uniq.append(x); seen.add(x)
                if len(uniq) >= max_docs:
                    break
            self.doc_by_node[roll_id] = uniq

    def answer(self, query: str) -> str:
        raw = ground(query, self.syn)
        raw = enrich_ground(query, raw)
        ICD_RE = re.compile(r'\b[A-TV-Z]\d[\dA-Z](?:\.?\d[\dA-Z]*)?\b')
 
        # collect codes
        seed_nodes = []
        proc_codes = set(raw.get("procedures", []))
        dx_codes   = set(raw.get("diagnoses", []))

        # enrich from query text
        for tok in ICD_RE.findall(query):
            dx_codes.add(tok.upper())

        # ensure every DX code exists as a node and is seeded
        for dxc in list(dx_codes):
            nid = self._by_code("Diagnosis", dxc)
            if not nid:
                nid = self._nid("Diagnosis", dxc)
                if nid not in self.G:
                    self.G.add_node(nid, label="Diagnosis", code=dxc, name=dxc)
            seed_nodes.append(nid)

        # Seeds + the literal codes we’ll test for membership
        for label, code in _iter_grounded(raw):
            nid = self._by_code(label, code)
            if nid:
                seed_nodes.append(nid)
            if label == "Procedure":
                proc_codes.add(code)
            elif label == "Diagnosis":
                dx_codes.add(code)
        CPT5 = re.compile(r"^\d{5}$")

        def _prefer_cpt(proc_codes: set[str]) -> set[str]:
            cpts = {c for c in proc_codes if CPT5.match(c)}
            return cpts or proc_codes  # if any 5-digit CPTs exist, ignore non-CPTs

        # in answer(), after collecting proc_codes:
        proc_codes = _prefer_cpt(proc_codes)
        proc_codes = {_canon_proc(c) for c in proc_codes}

        preferred_procs = _prefer_cpt(proc_codes)

        # Re-seed using only preferred procs
        seed_nodes = []
        for label, code in _iter_grounded(raw):
            if label == "Procedure":
                code = _canon_proc(code)
                if code not in preferred_procs:
                    continue  # drop PROC-123, etc.
            nid = self._by_code(label, code)
            if nid:
                seed_nodes.append(nid)
        
        # Ensure every CPT proc code exists as a node; seed it if missing
        for pc in list(proc_codes):
            nid = self._by_code("Procedure", pc)
            if not nid:
                nid = self._nid("Procedure", pc)
                if nid not in self.G:
                    self.G.add_node(nid, label="Procedure", code=pc, name=pc)
                seed_nodes.append(nid)

        # Double-guard: strip any stray non-preferred proc nodes
        seed_nodes = [
            n for n in seed_nodes
            if not (
                self.G.nodes[n].get("label") == "Procedure" and
                self.G.nodes[n].get("code") not in preferred_procs
            )
        ]

        if not seed_nodes:
            return "Couldn’t ground the jargon—include a procedure and a diagnosis."
        # If any DX seed is a roll-up, add its children to seeds (nice paths)
        extra = []
        for nid in list(seed_nodes):
            at = self.G.nodes[nid]
            if at.get('label') == "Diagnosis" and at.get('rollup'):
                for u, v, d in self.G.in_edges(nid, data=True):
                    if d.get('etype') == 'IS_A' and self.G.nodes[u].get('label') == "Diagnosis":
                        extra.append(u)
        seed_nodes.extend(extra)

        # ---- MULTI-MATCH MEMBERSHIP (no breaks) ----
        QG = self.G.copy()

        def add_edge_once(G, u, v, **attrs):
            for _, vv, dd in G.out_edges(u, data=True):
                if vv == v and all(dd.get(k) == attrs.get(k) for k in attrs):
                    return
            G.add_edge(u, v, **attrs)

        def attach_membership_edges(label: str, code: str, set_label: str, sid: str):
            nid = self._by_code(label, code) or self._nid(label, code)
            # ensure node exists in QG with attrs
            if nid not in QG:
                # copy attrs from master if present; else synthesize
                if nid in self.G:
                    QG.add_node(nid, **self.G.nodes[nid])
                else:
                    QG.add_node(nid, label=label, code=code, name=code)
            set_nid = self._nid(set_label, sid)
            if set_nid not in QG:
                # sets should exist from master; but just in case:
                attrs = self.G.nodes.get(set_nid, {"label": set_label, "code": sid, "set_id": sid, "name": sid})
                QG.add_node(set_nid, **attrs)
            add_edge_once(QG, nid, set_nid, etype="IS_IN")
            # roll-up child attachments for DX
            if label == "Diagnosis":
                at = QG.nodes[nid]
                if at.get("rollup") or str(code).upper().endswith(("X","*")):
                    for u, v, d in QG.in_edges(nid, data=True):
                        if d.get("etype") == "IS_A" and QG.nodes[u].get("label") == "Diagnosis":
                            add_edge_once(QG, u, set_nid, etype="IS_IN")

        matched_cov = []
        matched_sets_by_policy = {}             # cov_nid -> {"proc": set(), "dx": set()}
        dx_sets_any_by_code  = defaultdict(set) # dxc -> set(dx_set_ids) (policy-agnostic)
        dx_sets_qual_by_code = defaultdict(set) # dxc -> set(dx_set_ids) (policy+proc matched)
        dx_qual_policies     = defaultdict(set) # dxc -> set(policy_ids)

        for p in getattr(self, "_policies", []):
            pol_id = p["policy"]
            cov = self._nid("Coverage", pol_id)      # <-- use cov consistently
            psids = p.get("proc_sets", [])
            dsids = p.get("dx_sets",   [])

            proc_hits, dx_hits = set(), set()
            dx_hits_by_code_local = defaultdict(set)

            # PROCEDURES: only preferred CPTs
            for c in preferred_procs:
                for sid in psids:
                    if self._proc_in_set(c, sid):
                        proc_hits.add(sid)
                        attach_membership_edges("Procedure", c, "ProcSet", sid)  # adds to QG
                        add_edge_once(QG, cov, self._nid("ProcSet", sid), etype="USES_PROCSET")

            # DIAGNOSES
            for dxc in dx_codes:
                for sid in dsids:
                    if self._dx_in_set(dxc, sid):
                        dx_hits.add(sid)
                        dx_hits_by_code_local[dxc].add(sid)
                        dx_sets_any_by_code[dxc].add(sid)
                        attach_membership_edges("Diagnosis", dxc, "DxSet", sid)  # adds to QG
                        add_edge_once(QG, cov, self._nid("DxSet", sid), etype="USES_DXSET")

            matched_sets_by_policy[cov] = {"proc": proc_hits, "dx": dx_hits}

            # QUALIFY only when both sides hit under this policy
            if proc_hits and dx_hits:
                matched_cov.append(cov)
                for dxc, sids in dx_hits_by_code_local.items():
                    for sid in sids:
                        dx_sets_qual_by_code[dxc].add(sid)
                    dx_qual_policies[dxc].add(pol_id)

        # ensure every DX appears (even if empty) for rendering
        for dxc in dx_codes:
            dx_sets_any_by_code.setdefault(dxc, set())
            dx_sets_qual_by_code.setdefault(dxc, set())
            dx_qual_policies.setdefault(dxc, set())


        # Expand enough to include sets & policies
        SG = expand_subgraph(G=QG, seeds=seed_nodes, depth=3)

        focus_proc_nodes = {
            (self._by_code("Procedure", c) or self._nid("Procedure", c))
            for c in preferred_procs
        }
        SG = expand_subgraph(G=QG, seeds=seed_nodes, depth=3)
        facts = analyze(SG, seed_nodes, focus_procs=focus_proc_nodes)
        # include matched sets for the renderer (optional)
        facts.setdefault("matched_sets_by_policy", matched_sets_by_policy)
        facts.setdefault("policies", matched_cov)
        facts.setdefault("dx_sets_any_by_code",  {k: sorted(v) for k,v in dx_sets_any_by_code.items()})
        facts.setdefault("dx_sets_qual_by_code", {k: sorted(v) for k,v in dx_sets_qual_by_code.items()})
        facts.setdefault("dx_qual_policies",     {k: sorted(v) for k,v in dx_qual_policies.items()})

        # ---- Enrich facts for the renderer (safe no-ops if analyze already set them) ----
        # Flatten across policies for quick “matched sets” badges
        all_proc_sets = set().union(*(v["proc"] for v in matched_sets_by_policy.values())) if matched_sets_by_policy else set()
        all_dx_sets   = set().union(*(v["dx"]   for v in matched_sets_by_policy.values())) if matched_sets_by_policy else set()

        facts.setdefault("policies", matched_cov)
        facts.setdefault("matched_sets_by_policy", matched_sets_by_policy)
        facts.setdefault("matched_sets", {"proc": all_proc_sets, "dx": all_dx_sets})

        facts["dx_sets_any_by_code"]  = {k: sorted(v) for k, v in dx_sets_any_by_code.items()}
        facts["dx_sets_qual_by_code"] = {k: sorted(v) for k, v in dx_sets_qual_by_code.items()}
        facts["dx_qual_policies"]     = {k: sorted(v) for k, v in dx_qual_policies.items()}

        # Ensure sets/policies are eligible for citations
        nodes_seen = set(facts.get("nodes_seen", facts.get("seeds", [])))
        nodes_seen |= set(matched_cov)
        for s in all_proc_sets:
            nodes_seen.add(self._nid("ProcSet", s))
        for s in all_dx_sets:
            nodes_seen.add(self._nid("DxSet", s))
        facts["nodes_seen"] = list(nodes_seen)
        return render_answer(facts, self.doc_by_node, SG=SG)


    def add_policies_from_yaml(self, policy_data: dict):
        for p in policy_data.get("policies", []):
            pol_id = self._nid("Coverage", p["policy"])   # COV:cms-arthro
            if pol_id not in self.G:
                self.G.add_node(pol_id, label="Coverage",
                                policy=p["policy"], name=p.get("title") or p["policy"])
            # Procedure link
            px_id = self._nid("Procedure", p["procedure"])  # PX:PROC-123
            if px_id in self.G and not any(v == pol_id and d.get('etype') == 'COVERED_FOR'
                                        for _, v, d in self.G.out_edges(px_id, data=True)):
                self.G.add_edge(px_id, pol_id, etype="COVERED_FOR")
            # Diagnosis links (wildcards allowed)
            for dx in p.get("diagnoses", []):
                dx_id = self._nid("Diagnosis", dx)          # DX:M75.0x
                if dx_id not in self.G:  # optional placeholder; _by_code can also create
                    self.G.add_node(dx_id, label="Diagnosis", code=dx,
                                    name=dx, rollup=dx.endswith(('*','x','X')))
                if not any(v == pol_id and d.get('etype') == 'QUALIFIES_FOR'
                        for _, v, d in self.G.out_edges(dx_id, data=True)):
                    self.G.add_edge(dx_id, pol_id, etype="QUALIFIES_FOR")

            # seed minimal doc so policy cites even without external docs
            self.doc_by_node.setdefault(pol_id, []).append({
                "doc_id": p["policy"],
                "text_short": p.get("title") or "Coverage policy"
            })