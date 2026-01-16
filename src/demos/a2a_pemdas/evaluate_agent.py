import ast
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import time
import uuid
from fractions import Fraction

import sys
from pathlib import Path

DEBUG = True
# If you haven't done `pip install -e .` yet, keep this fallback:
REPO_ROOT = Path(__file__).resolve().parents[2]  # adjust if your layout differs
sys.path.insert(0, str(REPO_ROOT / "src"))
from a2a.core import AgentCard
from a2a.server import create_a2a_app, build_task_result

from a2a.client import a2a_send  # your canonical a2a_send(base_url, *, req_id, msg_obj)
from a2a.envelope import make_endpoint, make_response
from a2a.validate import validate_envelope_and_payload
from demos.a2a_pemdas.ast_utils import Num, Bin, parse_expression, render_pretty, render_debug, is_reducible
from demos.a2a_pemdas.rat_numbers import frac_to_rat, rat_to_frac, to_wire


# ----------------------------
# Config: where ADD/MULT live
# ----------------------------
# Defaulting to: ADD=8101, MULT=8102 
ADD_BASE  = os.getenv("ADD_BASE_URL",  "http://127.0.0.1:8101")
MULT_BASE = os.getenv("MULT_BASE_URL", "http://127.0.0.1:8102")


CARD = AgentCard(
    name="EVALUATE",
    version="0.1.0",
    url="http://127.0.0.1:8100",
    skills=["pemdas.eval", "routing"],
    raw={
        "accepts": ["a2a.request:v1"],
        "produces": ["a2a.response:v1"],
        "message_types": ["pemdas.eval:v1"],
        "depends_on": [
            {"skill": "pemdas.add", "url": ADD_BASE},
            {"skill": "pemdas.mult", "url": MULT_BASE},
        ],
    },
    card_sha256="",
)

SELF_ENDPOINT = make_endpoint(name=CARD.name, version=CARD.version, url=CARD.url, skill="pemdas.eval")
ADD_ENDPOINT  = make_endpoint(name="ADD",  url=ADD_BASE,  skill="pemdas.add")
MULT_ENDPOINT = make_endpoint(name="MULT", url=MULT_BASE, skill="pemdas.mult")


def _nope(x): raise ValueError(f"Non-finite constant in JSON: {x}")

def json_safe(obj):
    if isinstance(obj, Fraction):
        return {"type": "rat:v1", "n": obj.numerator, "d": obj.denominator}
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    if isinstance(obj, tuple):
        return [json_safe(x) for x in obj]
    return obj

def _ast_to_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Num(float(node.value))

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _ast_to_node(node.operand)
        if not isinstance(inner, Num):
            raise ValueError("Unary +/- only supported on numeric literals in v1")
        return Num(inner.v if isinstance(node.op, ast.UAdd) else -inner.v)

    if isinstance(node, ast.BinOp):
        left = _ast_to_node(node.left)
        right = _ast_to_node(node.right)

        if isinstance(node.op, ast.Add):
            return Bin("+", left, right)
        if isinstance(node.op, ast.Sub):
            return Bin("-", left, right)
        if isinstance(node.op, ast.Mult):
            return Bin("*", left, right)
        if isinstance(node.op, ast.Div):
            return Bin("/", left, right)

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def render(node: Any) -> str:
    if isinstance(node, Num):
        if node.v.is_integer():
            return str(int(node.v))
        return str(node.v)
    if isinstance(node, Bin):
        return f"({render(node.left)}{node.op}{render(node.right)})"
    raise TypeError("Unknown node type")


# ----------------------------
# Envelope call helpers
# ----------------------------
def _extract_child_result(task: Dict[str, Any], *, expected_op: str) -> Dict[str, Any]:
    """
    task is the JSON-RPC result object returned by a2a_send (your TASK RESULT).
    We expect task["meta"] to be an a2a.response:v1 envelope.
    Return the inner pemdas.result:v1 payload dict.
    """
    env = task["meta"]
    validate_envelope_and_payload(env, kind="response")

    if not env.get("ok", False):
        raise RuntimeError(f"Child error: {env.get('error')}")

    payload = env.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Child response missing payload object")

    if payload.get("type") != "pemdas.result:v1":
        raise ValueError(f"Expected pemdas.result:v1 payload, got {payload.get('type')}")

    if payload.get("op") != expected_op:
        raise ValueError(f"Expected op={expected_op}, got {payload.get('op')}")

    return payload


def call_add(req_env: Dict[str, Any], a: Fraction, b: Fraction, step_req_id: str) -> Tuple[Fraction, float]:
    t0 = time.perf_counter()

    child_req = {
        "type": "a2a.request:v1",
        "timestamp": req_env["timestamp"],     # ok to reuse
        "request_id": step_req_id,             # must be UUID string
        "trace_id": req_env["trace_id"],
        "message_type": "pemdas.add:v1",
        "payload": {
            "type": "pemdas.add:v1",
            "a": frac_to_rat(a),
            "b": frac_to_rat(b),
        },
        "source": SELF_ENDPOINT,
        "dest": ADD_ENDPOINT,
    }
    validate_envelope_and_payload(child_req, kind="request")

    task = a2a_send(ADD_BASE, req_id=child_req["request_id"], msg_obj=child_req)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    payload = _extract_child_result(task, expected_op="add")

    out_rat = payload["result"]          # <-- THIS is where result lives
    out_frac = rat_to_frac(out_rat)      # Fraction
    return out_frac, latency_ms

def call_mult(req_env: Dict[str, Any], a: Fraction, b: Fraction, step_req_id: str) -> Tuple[Fraction, float]:
    t0 = time.perf_counter()

    child_req = {
        "type": "a2a.request:v1",
        "timestamp": req_env["timestamp"],
        "request_id": step_req_id,
        "trace_id": req_env["trace_id"],
        "message_type": "pemdas.mult:v1",
        "payload": {
            "type": "pemdas.mult:v1",
            "a": frac_to_rat(a),
            "b": frac_to_rat(b),
        },
        "source": SELF_ENDPOINT,
        "dest": MULT_ENDPOINT,
    }
    validate_envelope_and_payload(child_req, kind="request")

    task = a2a_send(MULT_BASE, req_id=child_req["request_id"], msg_obj=child_req)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    payload = _extract_child_result(task, expected_op="mult")

    out_rat = payload["result"]
    out_frac = rat_to_frac(out_rat)
    return out_frac, latency_ms



# ----------------------------
# One-step reducer
# ----------------------------
def reduce_once(node: Any, req_env: Dict[str, Any], step_index: int) -> Tuple[Any, Optional[Dict[str, Any]]]:
    print("DEBUG node type:", type(node), "module:", type(node).__module__)
    if isinstance(node, Num):
        return node, None

    if isinstance(node, Bin):
        new_left, step = reduce_once(node.left, req_env, step_index)
        if step is not None:
            return Bin(node.op, new_left, node.right), step

        new_right, step = reduce_once(node.right, req_env, step_index)
        if step is not None:
            return Bin(node.op, node.left, new_right), step

        if isinstance(node.left, Num) and isinstance(node.right, Num):
            a = node.left.v
            b = node.right.v

            if not (math.isfinite(a) and math.isfinite(b)):
                raise ValueError("Inputs must be finite numbers")

            if DEBUG:
                before = render_debug(node)
            else:
                before = render_pretty(node)


            # IMPORTANT: request_id must be a UUID to satisfy your schema.
            # Use uuid4 strings; I’m leaving a placeholder generator here.
            import uuid
            step_req_id = str(uuid.uuid4())
            trace_id = req_env["trace_id"]

            if node.op == "+":
                out, ms = call_add(req_env, a, b, step_req_id)
                call = {
                    "agent": "ADD",
                    "dest_url": ADD_BASE,
                    "trace_id": trace_id,
                    "message_type": "pemdas.add:v1",
                    "a": frac_to_rat(a),
                    "b": frac_to_rat(b),
                    "request_id": step_req_id,
                    "latency_ms": round(ms, 3),
                }

            elif node.op == "-":
                out, ms = call_add(req_env, a, -b, step_req_id)
                call = {
                    "agent": "ADD",
                    "dest_url": ADD_BASE,
                    "trace_id": trace_id,
                    "message_type": "pemdas.add:v1",
                    "a": frac_to_rat(a),
                    "b": frac_to_rat(-b),
                    "request_id": step_req_id,
                    "latency_ms": round(ms, 3),
                    "note": "sub implemented as add(a, -b)",
                }

            elif node.op == "*":
                out, ms = call_mult(req_env, a, b, step_req_id)
                call = {
                    "agent": "MULT",
                    "dest_url": MULT_BASE,
                    "trace_id": trace_id,
                    "message_type": "pemdas.mult:v1",
                    "a": frac_to_rat(a),
                    "b": frac_to_rat(b),
                    "request_id": step_req_id,
                    "latency_ms": round(ms, 3),
                }

            elif node.op == "/":
                if b == 0:
                    raise ValueError("Division by zero")
                inv_b = Fraction(1, 1) / b   # exact reciprocal, still a Fraction
                out, ms = call_mult(req_env, a, inv_b, step_req_id)
                call = {
                    "agent": "MULT",
                    "dest_url": MULT_BASE,
                    "trace_id": trace_id,
                    "message_type": "pemdas.mult:v1",
                    "a": frac_to_rat(a),
                    "b": frac_to_rat(inv_b),
                    "request_id": step_req_id,
                    "latency_ms": round(ms, 3),
                    "note": "div implemented as mult(a, 1/b)",
                }
            else:
                raise ValueError(f"Unsupported op: {node.op}")

            step_trace = {
                "i": step_index,
                "before": before,
                "call": call,
                "result": frac_to_rat(out),
            }
            if not isinstance(out, Fraction):
                raise TypeError(f"Reducer produced non-Fraction out={out!r} ({type(out).__name__}). Fix call_add/call_mult or division.")
            return Num(out), step_trace

        return node, None

    raise TypeError("Unknown node type")


def evaluate_expression(req_env: Dict[str, Any], expr: str, max_steps: int = 100) -> Dict[str, Any]:
    root = parse_expression(expr)
    steps = []

    for i in range(1, max_steps + 1):
        new_root, step = reduce_once(root, req_env, i)
        root = new_root
        if step:
            step["after"] = render(root)
            steps.append(step)
        else:
            break

    if not isinstance(root, Num):
        raise ValueError("Expression did not fully reduce (v1 only supports numeric literals)")

    return {
        "ok": True,
        "type": "pemdas.eval.result:v1",
        "expression": expr,
        "final": render(root),
        "result": root.v,
        "steps": steps,
        "step_count": len(steps),
    }


# ----------------------------
# Brain
# ----------------------------
def eval_brain(text: str) -> Dict[str, Any]:
    req_env = json.loads(text, parse_constant=_nope)

    # Validate the envelope + its payload
    validate_envelope_and_payload(req_env, kind="request")

    if req_env["message_type"] != "pemdas.eval:v1":
        raise ValueError(f"EVALUATE cannot handle message_type={req_env['message_type']}")

    p = req_env["payload"]
    expr = p["expression"]
    max_steps = int(p.get("max_steps", 100))

    result_payload = evaluate_expression(req_env, expr, max_steps=max_steps)
    result_payload = to_wire(result_payload)
    resp_env = make_response(
        req=req_env,
        message_type="pemdas.eval.result:v1",
        source=SELF_ENDPOINT,
        dest=req_env["source"],
        ok=True,
        payload=result_payload,
    )
    resp_env = to_wire(resp_env)

    # Validate response envelope + payload
    validate_envelope_and_payload(resp_env, kind="response")

    return build_task_result(
        artifact_name="pemdas.eval.result",
        parts=[{"type": "text", "text": json.dumps(json_safe(resp_env))}],
        meta=resp_env,
    )


app = create_a2a_app(CARD, eval_brain)
