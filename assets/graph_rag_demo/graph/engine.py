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
from .params import CPT5, SHORT, ICD_RE, norm_code



# Ensure edges are not duplicated
def add_edge_once(G, u, v, **attrs):
    for _, vv, dd in G.out_edges(u, data=True):
        if vv == v and all(dd.get(k) == attrs.get(k) for k in attrs):
            return
    G.add_edge(u, v, **attrs)

    

def _iter_grounded(raw, *, stable=False, dedupe=False):
    """
    Normalize a heterogeneous grounding result into (label, code) pairs.
    - key2label: dict mapping bucket keys to default labels.
    - stable: deterministic ordering (sorts buckets/items).
    - dedupe: remove duplicate (label, code).
    """
    if not raw:
        return
    
    key2label = {
        "procedures": "Procedure",
        "diagnoses":  "Diagnosis",
        "modifiers":  "Modifier",
        "coverage":   "Coverage",
    }

    buckets = raw.items()
    if stable:
        buckets = sorted(buckets, key=lambda kv: kv[0])

    seen = set()
    for key, items in buckets:
        default_label = key2label.get(key)  # <- crucial
        seq = list(items) if not isinstance(items, list) else items
        if stable:
            seq = sorted(seq, key=lambda x: str(x))

        for it in seq:
            out_pairs = []  # zero, one, or multiple (label, code)

            if isinstance(it, tuple):
                if len(it) == 3:
                    # e.g. ("arthrocentesis","Procedure","PROC-123")
                    _, label, code = it
                    out_pairs.append((label, code))
                elif len(it) == 2:
                    # e.g. ("PROC-123","20610") or ("Procedure","20610")
                    a, b = it
                    if default_label and not any(x in (a,b) for x in ("Procedure","Diagnosis","Modifier","Coverage")):
                        out_pairs.append((default_label, b))
                    else:
                        # assume (label, code)
                        out_pairs.append((a, b))

            elif isinstance(it, dict):
                # {"term": "...", "label": "Procedure", "code": "20610"}
                label = it.get("label") or default_label
                code  = it.get("code")
                if label and code:
                    out_pairs.append((label, code))

            elif isinstance(it, str):
                s = it.strip()
                if ":" in s:
                    lbl, code = s.split(":", 1)
                    out_pairs.append((lbl, code))
                elif default_label:
                    # trust the bucket label
                    out_pairs.append((default_label, s))
                else:
                    # last-ditch heuristic
                    guesses = []
                    if any(ch.isalpha() for ch in s):  # looks like ICD-ish
                        guesses.append(("Diagnosis", s))
                    if s.isdigit():
                        guesses.append(("Procedure", s))
                    if not guesses:
                        guesses = [("Procedure", s), ("Diagnosis", s)]
                    out_pairs.extend(guesses)

            # yield, with optional dedupe + light normalization
            for (lbl, code) in out_pairs:
                lbl = (lbl or "").strip().title()
                code = (str(code) or "").strip()
                if not lbl or not code:
                    continue
                if dedupe:
                    k = (lbl, code)
                    if k in seen:
                        continue
                    seen.add(k)
                yield (lbl, code)


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
            # Remove wildcard and dot in a ICD code
            pref = spec.get('pattern', '').upper().replace('.', '').strip()
            if pref.endswith(('X','*')):
                pref = pref[:-1]
            return bool(pref) and norm_code(code).startswith(pref)

        if kind == 'dx_list':
            # Prefer a pre-normalized membership set if your index provides it
            members_norm = spec.get('members_norm')
            if isinstance(members_norm, set):
                return norm_code(code) in members_norm
            # Fallback: normalize on the fly
            members = spec.get('members') or []
            return norm_code(code) in {norm_code(x) for x in members}

        if kind == 'icd_range':
            start = norm_code(spec.get('start', ''))
            end   = norm_code(spec.get('end', ''))
            c     = norm_code(code)
            return len(c) == len(start) == len(end) and start <= c <= end

        return False

    def _attach_rollup_children(self, QG, seed_nodes, max_children=3):
        """
        For any Diagnosis seed that is a roll-up (e.g., M75.0x), import a few specific
        children (M75.00, M75.01, M75.02) and the IS_A edges into QG, so the 'Why'
        shows concrete codes. Optionally add them to seeds.
        """
        def add_node_from_master(nid):
            if nid in QG:
                return
            attrs = dict(self.G.nodes[nid]) if nid in self.G else {}
            if not attrs:
                return
            QG.add_node(nid, **attrs)

        # collect roll-up DX seeds in QG
        rollups = []
        for nid in list(seed_nodes):
            at = QG.nodes.get(nid, {})
            if at.get("label") == "Diagnosis" and at.get("rollup"):
                rollups.append(nid)

        for rid in rollups:
            # Prefer children already present in the master graph with explicit IS_A to the roll-up
            kids = []
            for u, v, d in self.G.in_edges(rid, data=True):
                if d.get("etype") == "IS_A" and self.G.nodes[u].get("label") == "Diagnosis":
                    kids.append(u)

            # If there are many, keep a small, stable subset for readability
            kids = sorted(kids)[:max_children]

            for kid in kids:
                add_node_from_master(kid)      # bring child node into QG
                add_node_from_master(rid)      # ensure roll-up is in QG
                # add IS_A edge kid -> roll-up (dedup)
                exists = any(v == rid and ed.get("etype") == "IS_A"
                            for _, v, ed in QG.out_edges(kid, data=True))
                if not exists:
                    QG.add_edge(kid, rid, etype="IS_A")
                # Optionally: let seeds include a couple specifics so expand_subgraph keeps them
                seed_nodes.add(kid)

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

    # Answers the query. 4 steps: Ground, Attach, Policy Check, and Render
    def answer(self, query: str) -> str:
        # GROUND
        # Goal: turn messy text into clean, deterministic (label, code) pairs + code sets.
        # Input: query, known synonyms (and optionally an LLM)
        # Output: pairs, proc_codes, dx_codes, modifiers
            # Convert query into dict of signals, there the keys are Procedure, Diagnosis, Modifier
        raw = ground(query, self.syn)
        pairs = list(_iter_grounded(raw, stable=True, dedupe=True))
        proc_codes = {c for (l,c) in pairs if l=="Procedure"}
        dx_codes   = {c for (l,c) in pairs if l=="Diagnosis"}
        for tok in ICD_RE.findall(query): dx_codes.add(tok.upper())

        def _prefer_cpt(codes): 
            cpts = {c for c in codes if CPT5.match(c)}
            return cpts or codes
        preferred_procs = _prefer_cpt(proc_codes)

        # ATTACH
        # Goal: materialize what the query needs:
        # - ensure the code nodes exist,
        # - add membership (IS_IN) edges from codes to the sets they hit,
        # - ensure policy nodes connect to the relevant sets (USES_*).
        # Do this in a small per-query graph QG (or a copy/induced subgraph) to avoid leakage.
        QG = nx.MultiDiGraph()
        seed_nodes = set()

        def ensure(label, code):
            nid = self._by_code(label, code) or self._nid(label, code)
            if nid not in QG:
                # clone attrs if exists in self.G, else synthesize
                attrs = dict(self.G.nodes[nid]) if nid in self.G else {"label":label,"code":code,"name":code}
                QG.add_node(nid, **attrs)
            seed_nodes.add(nid)
            return nid

        # seed DX + preferred PX
        for dxc in dx_codes: ensure("Diagnosis", dxc)
        for pc  in preferred_procs: ensure("Procedure", pc)

        def add_edge_once(G,u,v,**attrs):
            for _,vv,dd in G.out_edges(u, data=True):
                if vv==v and all(dd.get(k)==attrs.get(k) for k in attrs): return
            G.add_edge(u,v,**attrs)

        def attach_membership_edges(label, code, set_label, sid):
            node = ensure(label, code)
            set_nid = self._nid(set_label, sid)
            if set_nid not in QG:
                # bring set node & attrs from master graph/index
                spec = self._get_set_spec(sid) or {}
                QG.add_node(set_nid, label=set_label, set_id=sid, code=sid,
                            kind=spec.get("kind",""), name=sid)
            add_edge_once(QG, node, set_nid, etype="IS_IN")



        # For each policy, connect its ProcSets/DxSets and attach membership edges for matches
        matched_cov = []
        matched_sets_by_policy = {}

        for p in getattr(self, "_policies", []):
            pol_id = p["policy"]
            cov = self._nid("Coverage", pol_id)
            # pull coverage node into QG
            if cov not in QG:
                QG.add_node(cov, **self.G.nodes.get(cov, {"label":"Coverage","policy":pol_id,"name":pol_id}))

            proc_hits, dx_hits = set(), set()

            for c in preferred_procs:
                for sid in p.get("proc_sets", []):
                    if self._proc_in_set(c, sid):
                        proc_hits.add(sid)
                        attach_membership_edges("Procedure", c, "ProcSet", sid)
                        add_edge_once(QG, cov, self._nid("ProcSet", sid), etype="USES_PROCSET")

            for dxc in dx_codes:
                for sid in p.get("dx_sets", []):
                    if self._dx_in_set(dxc, sid):
                        dx_hits.add(sid)
                        attach_membership_edges("Diagnosis", dxc, "DxSet", sid)
                        add_edge_once(QG, cov, self._nid("DxSet", sid), etype="USES_DXSET")

            matched_sets_by_policy[cov] = {"proc": proc_hits, "dx": dx_hits}
            if proc_hits and dx_hits:
                matched_cov.append(cov)

        # Link child diagnoses to parent family
        self._attach_rollup_children(QG, seed_nodes, max_children=3)
        

        # POLICY_CHECK (compute the verdict from attached edges)
        # Goal: intersect the sets per policy and compute facts. No new edges—pure reading.
        SG = expand_subgraph(G=QG, seeds=list(seed_nodes), depth=3)

        # covered if any policy has both proc and dx hits
        covered = any(v["proc"] and v["dx"] for v in matched_sets_by_policy.values())

        facts = analyze(SG, list(seed_nodes), focus_procs={
            (self._by_code("Procedure", c) or self._nid("Procedure", c)) for c in preferred_procs
        })
        facts["covered"] = covered
        facts["policies"] = list(matched_cov)
        facts["matched_sets_by_policy"] = matched_sets_by_policy

        # RENDER: give the answer
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