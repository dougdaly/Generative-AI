import json
from typing import Any, Dict, List, Tuple

from a2a.core import AgentCard
from a2a.server import create_a2a_app, build_task_result
from a2a.envelope import make_endpoint, make_response
from a2a.validate import validate_envelope_and_payload

CARD = AgentCard(
    name="VALIDATE",
    version="0.1.0",
    url="http://127.0.0.1:8203",
    skills=["supply.validate"],
    raw={
        "accepts": ["a2a.request:v1"],
        "produces": ["a2a.response:v1"],
        "message_types": ["supply.validate:v1"],
    },
    card_sha256="",
)

SELF = make_endpoint(name=CARD.name, version=CARD.version, url=CARD.url, skill="supply.validate")

def _validate_plan(problem: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []

    # ----- Coverage -----
    required_ids = [c["id"] for c in problem["components"]]
    required_set = set(required_ids)

    sources = plan["component_sources"]
    plan_ids = [x["component_id"] for x in sources]
    plan_set = set(plan_ids)

    missing = [cid for cid in required_ids if cid not in plan_set]
    extra = [cid for cid in plan_ids if cid not in required_set]

    if missing:
        reasons.append(f"missing_components: {', '.join(missing)}")
    if extra:
        reasons.append(f"extra_components: {', '.join(extra)}")

    dupes = sorted({cid for cid in plan_ids if plan_ids.count(cid) > 1})
    if dupes:
        reasons.append(f"duplicate_component_sources: {', '.join(dupes)}")

    # ----- Existence -----
    sup_idx = {(s["component_id"], s["country"]): s for s in problem["suppliers"]}
    for src in sources:
        cid = src["component_id"]
        ctry = src["country"]
        if cid in required_set and (cid, ctry) not in sup_idx:
            reasons.append(f"unknown_supplier: component_id={cid} country={ctry}")

    assembly_idx = {a["country"] for a in problem["assembly_options"]}
    if plan["assembly_country"] not in assembly_idx:
        reasons.append(f"unknown_assembly_country: {plan['assembly_country']}")

    ship_idx = {sh["mode"] for sh in problem["shipping_options"]}
    if plan["ship_mode"] not in ship_idx:
        reasons.append(f"unknown_ship_mode: {plan['ship_mode']}")

    # ----- Banned rules -----
    for rule in problem["constraints"]["banned"]:
        for src in sources:
            if (
                rule["component_id"] == src["component_id"]
                and rule["supplier_country"] == src["country"]
                and rule["ship_mode"] == plan["ship_mode"]
            ):
                reasons.append(
                    f"banned_route: component_id={src['component_id']} supplier_country={src['country']} ship_mode={plan['ship_mode']}"
                )

    # ----- Lead time constraint -----
    # total_lead_days = max(component_lead_days) + assembly_lead_days + shipping_lead_days
    component_leads = []
    for src in sources:
        s = sup_idx.get((src["component_id"], src["country"]))
        if s:
            component_leads.append(int(s["lead_days"]))

    assembly_by_country = {a["country"]: a for a in problem["assembly_options"]}
    shipping_by_mode = {sh["mode"]: sh for sh in problem["shipping_options"]}

    a = assembly_by_country.get(plan["assembly_country"])
    sh = shipping_by_mode.get(plan["ship_mode"])

    if component_leads and a and sh:
        total_lead_days = max(component_leads) + int(a["lead_days"]) + int(sh["lead_days"])
        max_allowed = int(problem["constraints"]["max_total_lead_days"])
        if total_lead_days > max_allowed:
            reasons.append(f"lead_time_exceeded: total={total_lead_days} max={max_allowed}")

    ok = len(reasons) == 0
    return {"type": "supply.validation:v1", "ok": ok, "reasons": reasons}


def validate_brain(text: str) -> Dict[str, Any]:
    req_env = json.loads(text)
    validate_envelope_and_payload(req_env, kind="request")

    if req_env["message_type"] != "supply.validate:v1":
        raise ValueError(f"VALIDATE cannot handle message_type={req_env['message_type']}")

    p = req_env["payload"]
    problem = p["problem"]
    plan = p["plan"]

    result_payload = _validate_plan(problem, plan)

    resp_env = make_response(
        req=req_env,
        message_type="supply.validation:v1",
        source=SELF,
        dest=req_env["source"],
        ok=True,                    # transport ok
        payload=result_payload,      # business ok inside payload
    )

    validate_envelope_and_payload(resp_env, kind="response")

    return build_task_result(
        artifact_name="supply.validate.result",
        parts=[{"type": "text", "text": json.dumps(resp_env)}],
        meta=resp_env,
    )


app = create_a2a_app(CARD, validate_brain)

