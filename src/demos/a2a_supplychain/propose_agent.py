from __future__ import annotations

import json
from typing import Any, Dict, List

from a2a.core import AgentCard
from a2a.server import create_a2a_app, build_task_result
from a2a.envelope import make_endpoint, make_response
from a2a.validate import validate_envelope_and_payload
import copy
import random
from typing import Any, Dict, List, Optional, Tuple

Plan = Dict[str, Any]
Problem = Dict[str, Any]


CARD = AgentCard(
    name="PROPOSE",
    version="0.1.0",
    card_sha256="",
    url="http://127.0.0.1:8201",
    skills=["supply.propose"],
    raw={
        "accepts": ["a2a.request:v1"],
        "produces": ["a2a.response:v1"],
        "message_types": ["supply.propose:v1"],
    },
)

SELF_ENDPOINT = make_endpoint(
    name=CARD.name,
    version=CARD.version,
    url=CARD.url,
    skill="supply.propose",
)


def _plan_key(plan: Plan) -> Tuple:
    # stable identity for dedupe
    sources = tuple(sorted(
        ((s["component_id"], s["country"]) for s in plan["component_sources"]),
        key=lambda x: x[0]
    ))
    return (sources, plan["assembly_country"], plan["ship_mode"])

def _max_total_allowed(problem: Problem) -> int:
    return int(problem["constraints"]["max_total_lead_days"])

def _supplier_lead_idx(problem: Problem) -> dict[tuple[str, str], int]:
    return {
        (s["component_id"], s["country"]): int(s["lead_days"])
        for s in problem["suppliers"]
    }

def _assembly_lead_idx(problem: Problem) -> dict[str, int]:
    return {a["country"]: int(a["lead_days"]) for a in problem["assembly_options"]}

def _ship_lead_idx(problem: Problem) -> dict[str, int]:
    return {sh["mode"]: int(sh["lead_days"]) for sh in problem["shipping_options"]}

def _max_supplier_lead(problem: Problem, plan: Plan) -> int:
    idx = _supplier_lead_idx(problem)
    leads = [idx[(cs["component_id"], cs["country"])] for cs in plan["component_sources"]]
    return max(leads) if leads else 0

def _plan_violates_banned(problem: Problem, plan: Plan) -> bool:
    banned = _banned_set(problem)
    ship = plan["ship_mode"]
    for cs in plan["component_sources"]:
        if (cs["component_id"], cs["country"], ship) in banned:
            return True
    return False



def _sorted_shipping_modes(problem: Problem) -> List[Dict[str, Any]]:
    return sorted(
        problem["shipping_options"],
        key=lambda s: (int(s["lead_days"]), float(s["cost"]), s["mode"])
    )


def _sorted_assemblies(problem: Problem) -> List[Dict[str, Any]]:
    return sorted(
        problem["assembly_options"],
        key=lambda a: (float(a["labor_cost"]), int(a["lead_days"]), a["country"])
    )


def _suppliers_by_component(problem: Problem) -> Dict[str, List[Dict[str, Any]]]:
    by_comp: Dict[str, List[Dict[str, Any]]] = {}
    for s in problem["suppliers"]:
        by_comp.setdefault(s["component_id"], []).append(s)
    # sort each bucket by cheap/fast/country (deterministic)
    for cid, lst in by_comp.items():
        by_comp[cid] = sorted(lst, key=lambda s: (float(s["unit_cost"]), int(s["lead_days"]), s["country"]))
    return by_comp


def _banned_set(problem: Problem) -> set[tuple[str, str, str]]:
    return {
        (r["component_id"], r["supplier_country"], r["ship_mode"])
        for r in problem["constraints"]["banned"]
    }


def _mutate_shipping(problem: Problem, plan: Plan, rng: random.Random) -> Plan:
    modes = _sorted_shipping_modes(problem)
    mode_list = [m["mode"] for m in modes]
    cur = plan["ship_mode"]

    if len(mode_list) <= 1:
        raise ValueError("No alternative shipping modes")

    asm_idx = _assembly_lead_idx(problem)
    ship_idx = _ship_lead_idx(problem)

    asm_country = plan["assembly_country"]
    if asm_country not in asm_idx:
        raise ValueError(f"Unknown assembly_country={asm_country}")

    max_total = _max_total_allowed(problem)
    max_sup = _max_supplier_lead(problem, plan)
    asm_lead = asm_idx[asm_country]

    feasible = []
    for mode in mode_list:
        if mode == cur:
            continue
        total = max_sup + asm_lead + ship_idx[mode]
        if total > max_total:
            continue

        # banned-route check (changing ship mode can make current suppliers illegal)
        test = dict(plan)
        test["ship_mode"] = mode
        if _plan_violates_banned(problem, test):
            continue

        feasible.append(mode)

    if not feasible:
        raise ValueError("No feasible shipping swap under constraints")

    plan["ship_mode"] = rng.choice(feasible)
    return plan


def _mutate_assembly(problem: Problem, plan: Plan, rng: random.Random) -> Plan:
    assemblies = _sorted_assemblies(problem)
    country_list = [a["country"] for a in assemblies]
    cur = plan["assembly_country"]

    if len(country_list) <= 1:
        raise ValueError("No alternative assembly countries")

    asm_idx = _assembly_lead_idx(problem)
    ship_idx = _ship_lead_idx(problem)

    ship_mode = plan["ship_mode"]
    if ship_mode not in ship_idx:
        raise ValueError(f"Unknown ship_mode={ship_mode}")

    max_total = _max_total_allowed(problem)
    max_sup = _max_supplier_lead(problem, plan)
    ship_lead = ship_idx[ship_mode]

    feasible = []
    for ctry in country_list:
        if ctry == cur:
            continue
        if ctry not in asm_idx:
            continue
        total = max_sup + asm_idx[ctry] + ship_lead
        if total <= max_total:
            feasible.append(ctry)

    if not feasible:
        raise ValueError("No feasible assembly swap under constraints")

    plan["assembly_country"] = rng.choice(feasible)
    return plan



def _mutate_one_supplier(problem: Problem, plan: Plan, rng: random.Random) -> Plan:
    by_comp = _suppliers_by_component(problem)
    banned = _banned_set(problem)

    ship_mode = plan["ship_mode"]
    asm_country = plan["assembly_country"]

    asm_idx = _assembly_lead_idx(problem)
    ship_idx = _ship_lead_idx(problem)

    if asm_country not in asm_idx:
        raise ValueError(f"Unknown assembly_country={asm_country}")
    if ship_mode not in ship_idx:
        raise ValueError(f"Unknown ship_mode={ship_mode}")

    max_total = _max_total_allowed(problem)
    cap = max_total - asm_idx[asm_country] - ship_idx[ship_mode]
    if cap < 0:
        raise ValueError("No feasible supplier possible: cap < 0")

    # choose a component from the plan (not from problem), so we always have a current source
    cs_list = plan["component_sources"]
    if not cs_list:
        raise ValueError("Plan has no component_sources")

    j = rng.randrange(len(cs_list))
    cid = cs_list[j]["component_id"]
    cur_country = cs_list[j]["country"]

    options = by_comp.get(cid, [])
    if len(options) <= 1:
        raise ValueError(f"No alternative suppliers for component_id={cid}")

    feasible_countries = []
    for s in options:
        ctry = s["country"]
        if ctry == cur_country:
            continue
        if int(s["lead_days"]) > cap:
            continue
        if (cid, ctry, ship_mode) in banned:
            continue
        feasible_countries.append(ctry)

    if not feasible_countries:
        raise ValueError(f"No feasible supplier swap for component_id={cid}")

    cs_list[j]["country"] = rng.choice(feasible_countries)

    # sanity: ensure we didn't create a banned plan (paranoid but cheap)
    if _plan_violates_banned(problem, plan):
        raise ValueError("Mutation produced banned plan (unexpected)")

    return plan



def _apply_mutation(problem: Problem, plan: Plan, mutation: str, rng: random.Random) -> Plan:
    # Explicit mutation means: do it, or fail loudly.
    if mutation == "swap_shipping":
        return _mutate_shipping(problem, plan, rng)
    if mutation == "swap_assembly":
        return _mutate_assembly(problem, plan, rng)
    if mutation == "swap_one_supplier":
        return _mutate_one_supplier(problem, plan, rng)

    # "greedy" and "mixed": try a few different moves, but never return an infeasible neighbor.
    choices = ["swap_one_supplier", "swap_assembly", "swap_shipping"]
    rng.shuffle(choices)  # seedable via rng

    last_err: Exception | None = None
    for pick in choices:
        try:
            return _apply_mutation(problem, plan, pick, rng)
        except ValueError as e:
            last_err = e
            continue

    raise ValueError(f"No feasible mutation available from this plan. last_error={last_err}")


def _choose_fixed_plan(problem: dict) -> dict:
    components = problem["components"]               # [{id, qty}, ...]
    suppliers = problem["suppliers"]                 # [{component_id, country, unit_cost, lead_days}, ...]
    assemblies = problem["assembly_options"]         # [{country, labor_cost, lead_days}, ...]
    shippers = problem["shipping_options"]           # [{mode, cost, lead_days}, ...]

    # Identify min lead time for assembly & ship to see if supplier is worth considering
    max_total = int(problem["constraints"]["max_total_lead_days"])
    min_assembly = min(int(a["lead_days"]) for a in problem["assembly_options"])
    min_ship = min(int(s["lead_days"]) for s in problem["shipping_options"])
    # If a component supplier lead alone exceeds what's even possible after the fastest assembly+ship,
    # that supplier can never be feasible.
    cap = max_total - (min_assembly + min_ship)
    cap = max(cap, 0)

    # pick ship mode first (cheap, deterministic)
    ship_mode = sorted(shippers, key=lambda s: (s["lead_days"], s["cost"], s["mode"]))[0]["mode"]

    # banned rules (optional filter to avoid obvious invalid plans)
    banned = {
        (r["component_id"], r["supplier_country"], r["ship_mode"])
        for r in problem["constraints"]["banned"]
    }

    # group suppliers by component
    by_comp: dict[str, list[dict]] = {}
    for s in suppliers:
        by_comp.setdefault(s["component_id"], []).append(s)

    component_sources = []
    for c in components:
        cid = c["id"]
        candidates = by_comp.get(cid, [])
        if not candidates:
            raise ValueError(f"No suppliers for component_id={cid}")

        feasible = [s for s in candidates if int(s["lead_days"]) <= cap]
        if not feasible:
            raise ValueError(f"No feasible suppliers for component_id={cid} under lead-time cap={cap}")
        candidates = feasible

        allowed = [s for s in candidates if (cid, s["country"], ship_mode) not in banned]
        if not allowed:
            raise ValueError(f"All feasible suppliers banned for component_id={cid} ship_mode={ship_mode}")

        chosen = sorted(allowed, key=lambda s: (s["unit_cost"], s["lead_days"], s["country"]))[0]
        component_sources.append({"component_id": cid, "country": chosen["country"]})

    assembly_country = sorted(assemblies, key=lambda a: (a["labor_cost"], a["lead_days"], a["country"]))[0]["country"]

    return {
        "type": "supply.plan:v1",
        "component_sources": component_sources,
        "assembly_country": assembly_country,
        "ship_mode": ship_mode,
    }


def propose_candidates(problem, *, n_candidates, mutation, seed, base_plan=None):
    base = copy.deepcopy(base_plan) if base_plan else _choose_fixed_plan(problem)

    # Fast path: tiny discrete neighborhood
    if mutation == "swap_shipping":
        modes = [s["mode"] for s in problem["shipping_options"]]
        alts = [m for m in modes if m != base["ship_mode"]]
        rng = random.Random(seed)
        rng.shuffle(alts)

        out = [base]
        for m in alts:
            if len(out) >= n_candidates:
                break
            p = copy.deepcopy(base)
            p["ship_mode"] = m
            out.append(p)
        return out  # no padding

    # Generic path (your current approach)
    seen, out = set(), []
    max_attempts = max(20, n_candidates * 10)
    for j in range(max_attempts):
        if len(out) >= n_candidates:
            break

        rng = random.Random((seed * 1_000_003) ^ (j * 9_973))
        plan = copy.deepcopy(base)
        try:
            plan = _apply_mutation(problem, plan, mutation, rng)
        except ValueError as e:
            #No feasible neighbor; skip this attempt
            continue

        k = _plan_key(plan)
        if k in seen:
            continue
        seen.add(k)
        out.append(plan)

    return out or [base]


def _build_propose_result_payload(candidates: list[dict]) -> dict:
    return {
        "type": "supply.propose.result:v1",
        "candidates": candidates,
    }


def propose_brain(text: str) -> Dict[str, Any]:
    req_env = json.loads(text)

    # 1) Validate request envelope + payload
    validate_envelope_and_payload(req_env, kind="request")

    if req_env["message_type"] != "supply.propose:v1":
        raise ValueError(f"PROPOSE cannot handle message_type={req_env['message_type']}")

    p = req_env["payload"]

    problem = p["problem"]

    candidates = propose_candidates(
        problem,
        n_candidates=int(p["n_candidates"]),
        mutation=p.get("mutation", "greedy"),
        seed=int(p.get("seed", 0)),
        base_plan=p.get("base_plan"),
    )

    result_payload = _build_propose_result_payload(candidates)

    resp_env = make_response(
        req=req_env,
        message_type="supply.propose.result:v1",
        source=SELF_ENDPOINT,
        dest=req_env["source"],
        ok=True,
        payload=result_payload,
    )

    # 2) Validate response envelope + payload
    validate_envelope_and_payload(resp_env, kind="response")

    return build_task_result(
        artifact_name="supply.propose.result",
        parts=[{"type": "text", "text": json.dumps(resp_env)}],
        meta=resp_env,
    )


app = create_a2a_app(CARD, propose_brain)

