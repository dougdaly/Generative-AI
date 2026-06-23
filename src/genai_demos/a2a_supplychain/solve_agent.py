import json, time, uuid
from typing import Any, Dict, List, Tuple

from a2a.core import AgentCard
from a2a.client import a2a_send
from a2a.envelope import make_endpoint, make_response
from a2a.server import create_a2a_app, build_task_result
from a2a.validate import validate_envelope_and_payload
import random
import math

PROPOSE_BASE  = "http://127.0.0.1:8201"
PRICE_BASE    = "http://127.0.0.1:8202"
VALIDATE_BASE = "http://127.0.0.1:8203"

CARD = AgentCard(
    name="SOLVE",
    version="0.1.0",
    url="http://127.0.0.1:8200",
    skills=["supply.solve"],
    raw={
        "accepts": ["a2a.request:v1"],
        "produces": ["a2a.response:v1"],
        "message_types": ["supply.solve:v1"],
        "depends_on": [
            {"skill": "supply.propose", "url": PROPOSE_BASE},
            {"skill": "supply.validate", "url": VALIDATE_BASE},
            {"skill": "supply.price", "url": PRICE_BASE},
        ],
    },
    card_sha256="",
)

SELF = make_endpoint(name=CARD.name, version=CARD.version, url=CARD.url, skill="supply.solve")
PROPOSE_EP  = make_endpoint(name="PROPOSE",  url=PROPOSE_BASE,  skill="supply.propose")
VALIDATE_EP = make_endpoint(name="VALIDATE", url=VALIDATE_BASE, skill="supply.validate")
PRICE_EP    = make_endpoint(name="PRICE",    url=PRICE_BASE,    skill="supply.price")

MUTATION_TO_ACTION = {
    "greedy": "seed_greedy",
    "swap_one_supplier": "mutate_supplier",
    "swap_assembly": "mutate_assembly",
    "swap_shipping": "mutate_shipping",
    "mixed": "mixed_mutation",
}


def _trace_event(*, eval_i, action, candidate, validation, price, best_so_far_cost, latency_ms=0.0, reason=None, note=None):
    ev = {
        "type": "supply.trace.event:v1", 
        "eval_i": int(eval_i),
        "action": action,
        "candidate": candidate,
        "validation": validation,
        "price": price,
        "best_so_far_cost": round(float(best_so_far_cost),2),
        "latency_ms": float(latency_ms),
    }
    if reason is not None:
        ev["reason"] = str(reason)
    if note is not None:
        ev["note"] = str(note)
    return ev


def _plan_key(plan: Dict[str, Any]) -> str:
    # Canonicalize for de-dupe. Stable JSON string works fine here.
    return json.dumps(plan, sort_keys=True, separators=(",", ":"))

def _extract_ok_payload(task: Dict[str, Any], expected_message_type: str) -> Dict[str, Any]:
    meta = task.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("Child call missing meta envelope")

    validate_envelope_and_payload(meta, kind="response")

    if meta.get("ok") is not True:
        raise RuntimeError(f"Child call failed: {meta.get('error')}")

    if meta.get("message_type") != expected_message_type:
        raise ValueError(f"Expected child message_type={expected_message_type}, got {meta.get('message_type')}")

    payload = meta.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Child payload missing or not an object")
    return payload

def _call_child(req_env: Dict[str, Any], *, base_url: str, dest_ep: Dict[str, Any],
               message_type: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    child_req = {
        "type": "a2a.request:v1",
        "timestamp": req_env["timestamp"],
        "request_id": str(uuid.uuid4()),
        "trace_id": req_env["trace_id"],
        "message_type": message_type,
        "payload": payload,
        "source": SELF,
        "dest": dest_ep,
    }
    validate_envelope_and_payload(child_req, kind="request")

    t0 = time.perf_counter()
    task = a2a_send(base_url, req_id=child_req["request_id"], msg_obj=child_req)
    ms = (time.perf_counter() - t0) * 1000.0
    return task, ms


def _seed_plan(req_env, problem, *, seed: int, max_tries: int = 5) -> dict:
    # 1) get a candidate from PROPOSE
    for i in range(max_tries):
        propose_payload = {
            "type": "supply.propose:v1",
            "problem": problem,
            "n_candidates": 1,
            "mutation": "greedy",
            "seed": seed + i,
        }
        task, propose_ms = _call_child(
            req_env,
            base_url=PROPOSE_BASE,
            dest_ep=PROPOSE_EP,
            message_type="supply.propose:v1",
            payload=propose_payload,
        )
        plan = _extract_ok_payload(task, "supply.propose.result:v1")["candidates"][0]

        # 2) validate
        v_payload = {"type": "supply.validate:v1", "problem": problem, "plan": plan}
        v_task, v_ms = _call_child(
            req_env,
            base_url=VALIDATE_BASE,
            dest_ep=VALIDATE_EP,
            message_type="supply.validate:v1",
            payload=v_payload,
        )
        validation = _extract_ok_payload(v_task, "supply.validation:v1")
        if validation["ok"]:
            return plan, propose_ms

    # If we never found a valid one, return the last plan anyway (or raise).
    return plan, propose_ms

def _eval_plan(req_env, problem, plan):
    v_payload = {"type": "supply.validate:v1", "problem": problem, "plan": plan}
    v_task, v_ms = _call_child(
        req_env, base_url=VALIDATE_BASE, dest_ep=VALIDATE_EP,
        message_type="supply.validate:v1", payload=v_payload
    )
    validation = _extract_ok_payload(v_task, "supply.validation:v1")

    if not validation["ok"]:
        price = {
            "type": "supply.price_breakdown:v1",
            "ok": False,
            "total_cost": 1e9,
            "total_lead_days": 10**9,
            "line_items": [{"kind": "penalty", "amount": 1e9}],
        }
        pr_ms = 0.0
    else:
        pr_payload = {"type": "supply.price:v1", "problem": problem, "plan": plan}
        pr_task, pr_ms = _call_child(
            req_env, base_url=PRICE_BASE, dest_ep=PRICE_EP,
            message_type="supply.price:v1", payload=pr_payload
        )
        price = _extract_ok_payload(pr_task, "supply.price_breakdown:v1")

    cost = round(float(price["total_cost"]), 2)
    return validation, price, cost, v_ms + pr_ms


def _solve_anneal(*, req_env, problem, budget: int, strategy_config: dict):
    params = strategy_config.get("params") or {}
    seed0 = int(params.get("random_seed", 0))
    rng = random.Random(seed0)

    anneal = (params.get("anneal") or {})
    t_start = float(anneal.get("t_start", 5.0))
    t_end   = float(anneal.get("t_end",   0.2))
    cooling = float(anneal.get("cooling", 0.97))

    trace = []

    # 0) seed (counts as eval #1)
    current, propose_ms = _seed_plan(req_env=req_env, problem=problem, seed=seed0)
    validation, price, current_cost, eval_ms = _eval_plan(req_env, problem, current)

    best_plan, best_price, best_cost = current, price, current_cost
    eval_used = 1
    T = t_start

    # seed trace
    seed_reason = None
    if not validation["ok"]:
        seed_reason = (validation.get("reasons") or ["invalid"])[0]

    trace.append(_trace_event(
        eval_i=eval_used,
        action="seed_greedy",
        candidate=current,
        validation=validation,
        price=price,
        best_so_far_cost=best_cost,
        latency_ms=round(propose_ms + eval_ms, 3),
        reason=seed_reason,  # make sure _trace_event omits the field when None
        note="anneal seed",
    ))

    mutations = ["swap_one_supplier", "swap_assembly", "swap_shipping"]
    while eval_used < budget:
        # 1) propose neighbor around current
        mut = rng.choice(mutations)  
        propose_payload = {
            "type": "supply.propose:v1",
            "problem": problem,
            "base_plan": current,
            "n_candidates": 1,
            "mutation": mut,
            "seed": seed0 + eval_used,
        }
        task, propose_ms = _call_child(
            req_env, base_url=PROPOSE_BASE, dest_ep=PROPOSE_EP,
            message_type="supply.propose:v1", payload=propose_payload
        )
        cand = _extract_ok_payload(task, "supply.propose.result:v1")["candidates"][0]

        # 2) evaluate
        validation, price, cost, eval_ms = _eval_plan(req_env, problem, cand)
        eval_used += 1

        # Snapshot current before we evaluate this candidate
        cur_before = float(current_cost)

        accept = False
        accept_reason = ""

        if not validation["ok"]:
            accept = False
            accept_reason = "invalid"
            delta = None
        else:
            delta = float(cost - cur_before)
            eps = 1e-9
            if delta <= eps:
                accept = True
                accept_reason = "better_or_equal"
            else:
                p_acc = math.exp(-delta / max(T, 1e-9))
                r = rng.random()
                accept = (r < p_acc)
                accept_reason = f"worse p={p_acc:.3f} r={r:.3f}"

        # Apply the move (only after we’ve computed/logged everything from cur_before)
        if accept and validation["ok"]:
            current, current_cost = cand, float(cost)

        if validation["ok"] and cost < best_cost:
            best_cost, best_plan, best_price = float(cost), cand, price

        reason = None
        if not validation["ok"]:
            reason = (validation.get("reasons") or ["invalid"])[0]

        # Log using cur_before and the delta computed against cur_before
        delta_str = "n/a" if delta is None else f"{delta:+.2f}"
        trace.append(_trace_event(
            eval_i=eval_used,
            action=MUTATION_TO_ACTION[mut],
            candidate=cand,
            validation=validation,
            price=price,
            best_so_far_cost=round(float(best_cost),2),
            latency_ms=round(propose_ms + eval_ms, 3),
            reason=reason,
            note=f"anneal T={T:.3f} cur={cur_before:.2f} cand={cost:.2f} delta={delta_str} "
                f"best={best_cost:.2f} accept={accept} ({accept_reason})"
        ))
        T = max(t_end, T * cooling)

    ok = bool(best_price) and bool(best_price.get("ok"))

    return {
        "type": "supply.solve.result:v1",
        "ok": ok,
        "best_plan": best_plan,
        "best_price": best_price,
        "evaluations_used": eval_used,
        "evaluation_budget": budget,
        "strategy_config": strategy_config,
        "trace": trace,
    }


def _solve_beam(*, req_env, problem, budget, strategy_config):
    params = (strategy_config.get("params") or {})
    beam_p = (params.get("beam") or {})
    K = int(beam_p.get("beam_width", 3))
    per_parent = int(beam_p.get("candidates_per_parent", 5))

    p = req_env["payload"]
    seed = int(p.get("seed", 0))
    trace = []
    seen = set()

    best_cost = float("inf")
    best_plan = None
    best_price = None

    # seed with one plan (use propose greedy once)
    base_plan, propose_ms = _seed_plan(req_env=req_env, problem=problem, seed=seed)
    frontier = [base_plan]

    eval_used = 0
    round_i = 0

    while eval_used < budget:
        round_i += 1
        candidates = []

        # Expand each plan in the frontier
        for parent in frontier:
            if eval_used >= budget:
                break

            propose_payload = {
                "type": "supply.propose:v1",
                "problem": problem,
                "base_plan": parent,
                "n_candidates": per_parent,
                "mutation": "swap_shipping",
                "seed": int(params.get("random_seed", 0)) + round_i,
            }
            task, propose_ms = _call_child(
                req_env,
                base_url=PROPOSE_BASE,
                dest_ep=PROPOSE_EP,
                message_type="supply.propose:v1",
                payload=propose_payload,
            )
            out = _extract_ok_payload(task, "supply.propose.result:v1")
            candidates.extend(out["candidates"])

        # De-dupe
        uniq = []
        for plan in candidates:
            k = _plan_key(plan)
            if k not in seen:
                seen.add(k)
                uniq.append(plan)

        # Evaluate uniq candidates (VALIDATE then PRICE)
        scored = []
        for plan in uniq:
            if eval_used >= budget:
                break
            eval_used += 1
            eval_i = eval_used

            validation, price, cost, eval_ms = _eval_plan(req_env, problem, plan)
            if cost < best_cost:
                best_cost, best_plan, best_price = cost, plan, price
            reasons = validation.get("reasons", []) or []
            invalid_reason = reasons[0] if reasons else "invalid"

            scored.append({
                "cost": cost,
                "plan": plan,
                "validation": validation,
                "price": price,
                "lat_ms": propose_ms + eval_ms,
                "invalid_reason": invalid_reason,
                "eval_i": eval_i,
            })

        # Keep best K as new frontier
        scored.sort(key=lambda r: r["cost"])
        kept = scored[:K]
        # Advance the beam frontier
        frontier = [r["plan"] for r in kept]
        if not frontier:
            break
        cutoff_cost = kept[-1]["cost"] if kept else float("inf")

        kept_set = {_plan_key(r["plan"]) for r in kept}
        for r in scored:
            is_kept = _plan_key(r["plan"]) in kept_set
            action = "beam_keep" if is_kept else "beam_drop"

            # reason only really matters for drops
            reason = None
            if not is_kept:
                if not r["validation"]["ok"]:
                    reason = f"invalid: {r['invalid_reason']}"
                else:
                    reason = f"worse_cost: {r['cost']:.2f} >= {cutoff_cost:.2f}"

            trace.append(_trace_event(
                eval_i=r["eval_i"],  
                action=action,
                candidate=r["plan"],
                validation=r["validation"],
                price=r["price"],
                best_so_far_cost=round(float(best_cost),2),
                latency_ms=round(r["lat_ms"], 3),
                reason=reason,
                note=f"beam_width={K} candidates_per_parent={per_parent}",
            ))
        if not scored:
            break  # nothing new to evaluate
    return {
        "type": "supply.solve.result:v1",
        "ok": best_plan is not None,
        "best_plan": best_plan,
        "best_price": best_price,
        "evaluations_used": eval_used,
        "evaluation_budget": budget,
        "strategy_config": strategy_config,
        "trace": trace,
    }


def _solve_greedy(*, req_env: dict, problem: dict, budget: int, strategy_config: dict) -> dict:
    p = req_env["payload"]
    n_candidates = int(p.get("n_candidates", 5))
    mutation = p.get("mutation", "greedy")
    seed = int(p.get("seed", 0))

    trace: List[Dict[str, Any]] = []
    best_plan = None
    best_price = None
    best_cost = float("inf")

    eval_used = 0
    seen = set()

    while eval_used < budget:
        # 1) PROPOSE
        propose_payload = {
            "type": "supply.propose:v1",
            "problem": problem,
            "n_candidates": n_candidates,
            "mutation": mutation,
            "seed": seed,
        }
        task, propose_ms = _call_child(
            req_env, base_url=PROPOSE_BASE, dest_ep=PROPOSE_EP,
            message_type="supply.propose:v1", payload=propose_payload
        )
        propose_out = _extract_ok_payload(task, "supply.propose.result:v1")
        cands = propose_out["candidates"]

        # 2) de-dupe
        uniq = []
        for plan in cands:
            k = _plan_key(plan)
            if k not in seen:
                seen.add(k)
                uniq.append(plan)

        # 3) evaluate candidates
        for plan in uniq:
            if eval_used >= budget:
                break
            eval_used += 1
            eval_i = eval_used

            # VALIDATE
            v_payload = {"type": "supply.validate:v1", "problem": problem, "plan": plan}
            v_task, v_ms = _call_child(
                req_env, base_url=VALIDATE_BASE, dest_ep=VALIDATE_EP,
                message_type="supply.validate:v1", payload=v_payload
            )
            v_out = _extract_ok_payload(v_task, "supply.validation:v1")
            v_ok = bool(v_out["ok"])
            v_reasons = v_out.get("reasons", [])

            if not v_ok:
                price = {
                    "type": "supply.price_breakdown:v1",
                    "ok": False,
                    "total_cost": 1e9,
                    "total_lead_days": 10**9,
                    "line_items": [{"kind": "penalty", "amount": 1e9}],
                }
            else:
                # PRICE
                pr_payload = {"type": "supply.price:v1", "problem": problem, "plan": plan}
                pr_task, pr_ms = _call_child(
                    req_env, base_url=PRICE_BASE, dest_ep=PRICE_EP,
                    message_type="supply.price:v1", payload=pr_payload
                )
                price = _extract_ok_payload(pr_task, "supply.price_breakdown:v1")

            cost = round(float(price["total_cost"]), 2)
            if cost < best_cost:
                best_cost = cost
                best_plan = plan
                best_price = price

            action_taken = MUTATION_TO_ACTION.get(mutation, "mixed_mutation")  # safe fallback
            cand_latency_ms = v_ms + (pr_ms if v_ok else 0.0)
            # log each candidate plan
            trace.append(_trace_event(
                eval_i=eval_i,
                action=action_taken,
                candidate=plan,
                validation=v_out,          # RESULT payload
                price=price,               # RESULT payload (even penalty one)
                best_so_far_cost=best_cost,
                latency_ms=round(cand_latency_ms, 3),
                reason=("; ".join(v_reasons) if v_reasons else None),
            ))


        seed += 1  # deterministic variety even before real mutations exist

        # When that happens, stop early:
        if len(uniq) == 0:
            break

    # Guarantee required fields even if nothing valid showed up.
    if best_plan is None:
        best_plan = cands[0]
        best_price = {
            "type": "supply.price_breakdown:v1",
            "ok": False,
            "total_cost": 1e9,
            "total_lead_days": 10**9,
            "line_items": [{"kind": "penalty", "amount": 1e9}],
        }
    return {
            "type": "supply.solve.result:v1",
            "ok": True,
            "best_plan": best_plan,
            "best_price": best_price,
            "evaluations_used": eval_used,
            "evaluation_budget": budget,
            "strategy_config": strategy_config,
            "trace": trace,
        }



def solve_brain(text: str) -> dict:
    req_env = json.loads(text)
    if req_env["message_type"] != "supply.solve:v1":
        raise ValueError(f"SOLVE cannot handle message_type={req_env['message_type']}")
    validate_envelope_and_payload(req_env, kind="request")

    p = req_env["payload"]
    problem = p["problem"]
    budget = int(p["evaluation_budget"])
    strategy_config = p["strategy_config"]
    strategy = strategy_config["strategy_selected"]

    if strategy == "greedy":
        result_payload = _solve_greedy(req_env=req_env, problem=problem, budget=budget, strategy_config=strategy_config)
    elif strategy == "beam":
        result_payload = _solve_beam(req_env=req_env, problem=problem, budget=budget, strategy_config=strategy_config)
    elif strategy == "anneal":
        result_payload = _solve_anneal(req_env=req_env, problem=problem, budget=budget, strategy_config=strategy_config)
    else:
        raise ValueError(f"Unsupported strategy_selected={strategy!r}")

    resp_env = make_response(
        req=req_env,
        message_type="supply.solve.result:v1",
        source=SELF,
        dest=req_env["source"],
        ok=True,
        payload=result_payload,
    )
    validate_envelope_and_payload(resp_env, kind="response")

    return build_task_result(
        artifact_name="supply.solve.result",
        parts=[{"type": "text", "text": json.dumps(resp_env)}],
        meta=resp_env,
    )


app = create_a2a_app(CARD, solve_brain)
