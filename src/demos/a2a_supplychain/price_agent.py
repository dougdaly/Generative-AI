import json
from typing import Any, Dict, List, Tuple

from a2a.core import AgentCard
from a2a.server import create_a2a_app, build_task_result
from a2a.envelope import make_endpoint, make_response
from a2a.validate import validate_envelope_and_payload

CARD = AgentCard(
    name="PRICE",
    version="0.1.0",
    url="http://127.0.0.1:8202",
    skills=["supply.price"],
    raw={
        "accepts": ["a2a.request:v1"],
        "produces": ["a2a.response:v1"],
        "message_types": ["supply.price:v1"],
    },
    card_sha256="",
)

SELF = make_endpoint(name=CARD.name, version=CARD.version, url=CARD.url, skill="supply.price")


def _index_problem(problem: Dict[str, Any]) -> Dict[str, Any]:
    qty_by_comp = {c["id"]: int(c["qty"]) for c in problem["components"]}
    supplier_idx = {(s["component_id"], s["country"]): s for s in problem["suppliers"]}
    assembly_by_country = {a["country"]: a for a in problem["assembly_options"]}
    ship_by_mode = {sh["mode"]: sh for sh in problem["shipping_options"]}

    comp_tariff = {(t["from"], t["to"]): float(t["rate"]) for t in problem["tariffs"]["component_import"]}
    fg_tariff = {t["from"]: float(t["rate"]) for t in problem["tariffs"]["finished_good_to_us"]}

    return {
        "qty_by_comp": qty_by_comp,
        "supplier_idx": supplier_idx,
        "assembly_by_country": assembly_by_country,
        "ship_by_mode": ship_by_mode,
        "comp_tariff": comp_tariff,
        "fg_tariff": fg_tariff,
        "max_lead": int(problem["constraints"]["max_total_lead_days"]),
    }


def _price(problem: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    idx = _index_problem(problem)

    assembly_country = plan["assembly_country"]
    ship_mode = plan["ship_mode"]

    assembly = idx["assembly_by_country"].get(assembly_country)
    ship = idx["ship_by_mode"].get(ship_mode)
    if not assembly:
        raise ValueError(f"Unknown assembly_country={assembly_country}")
    if not ship:
        raise ValueError(f"Unknown ship_mode={ship_mode}")

    component_cost = 0.0
    component_tariff = 0.0
    component_leads: List[int] = []

    for src in plan["component_sources"]:
        cid = src["component_id"]
        scountry = src["country"]
        qty = idx["qty_by_comp"].get(cid, 0)

        s = idx["supplier_idx"].get((cid, scountry))
        if not s:
            raise ValueError(f"Unknown supplier for component_id={cid} country={scountry}")

        unit_cost = float(s["unit_cost"])
        lead_days = int(s["lead_days"])
        component_leads.append(lead_days)

        base = qty * unit_cost
        component_cost += base

        rate = idx["comp_tariff"].get((scountry, assembly_country), 0.0)
        component_tariff += base * rate

    assembly_labor = float(assembly["labor_cost"])
    shipping_cost = float(ship["cost"])

    total_lead_days = (max(component_leads) if component_leads else 0) + int(assembly["lead_days"]) + int(ship["lead_days"])

    # finished-good tariff applies to “value at import”
    pre_fg_total = component_cost + component_tariff + assembly_labor + shipping_cost
    fg_rate = idx["fg_tariff"].get(assembly_country, 0.0)
    finished_good_tariff = pre_fg_total * fg_rate

    # Optional: penalty if lead time exceeds constraint (keeps solver from “winning” with invalid plans)
    penalty = 0.0
    if total_lead_days > idx["max_lead"]:
        penalty = 1_000.0 * (total_lead_days - idx["max_lead"])

    total_cost = pre_fg_total + finished_good_tariff + penalty
    total_cost = round(total_cost,2)
    ok = penalty == 0.0  # if you’d rather not treat as failure, set ok=True always

    line_items = [
        {"kind": "component_cost", "amount": component_cost},
        {"kind": "component_tariff", "amount": round(component_tariff,2)},
        {"kind": "assembly_labor", "amount": assembly_labor},
        {"kind": "shipping", "amount": shipping_cost},
        {"kind": "finished_good_tariff", "amount": round(finished_good_tariff,2)},
    ]
    if penalty:
        line_items.append({"kind": "penalty", "amount": penalty})

    return {
        "type": "supply.price_breakdown:v1",
        "ok": ok,
        "total_cost": total_cost,
        "total_lead_days": total_lead_days,
        "line_items": line_items,
    }


def price_brain(text: str) -> Dict[str, Any]:
    req_env = json.loads(text)
    validate_envelope_and_payload(req_env, kind="request")

    if req_env["message_type"] != "supply.price:v1":
        raise ValueError(f"PRICE cannot handle message_type={req_env['message_type']}")

    p = req_env["payload"]
    problem = p["problem"]
    plan = p["plan"]

    result_payload = _price(problem, plan)

    resp_env = make_response(
        req=req_env,
        message_type="supply.price_breakdown:v1",
        source=SELF,
        dest=req_env["source"],
        ok=True,
        payload=result_payload,
    )
    validate_envelope_and_payload(resp_env, kind="response")

    return build_task_result(
        artifact_name="supply.price.result",
        parts=[{"type": "text", "text": json.dumps(resp_env)}],
        meta=resp_env,
    )


app = create_a2a_app(CARD, price_brain)

