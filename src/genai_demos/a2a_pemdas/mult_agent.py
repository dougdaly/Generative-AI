import json
from typing import Any, Dict

import sys
from pathlib import Path

# Prefer editable install (pip install -e .). If not, keep this fallback.
REPO_ROOT = Path(__file__).resolve().parents[2]  # adjust if needed
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from a2a.core import AgentCard
from a2a.server import create_a2a_app, build_task_result

from a2a.envelope import make_endpoint, make_response
from a2a.validate import validate_envelope_and_payload
from demos.a2a_pemdas.rat_numbers import rat_to_frac, frac_to_rat, to_wire

# Add restriction to not allow infinity / null in arithmetic
def strict_json_loads(s: str) -> dict:
    def _nope(x):
        raise ValueError(f"Non-finite constant in JSON: {x}")
    return json.loads(s, parse_constant=_nope)

CARD = AgentCard(
    name="MULT",
    version="0.1.0",
    url="http://127.0.0.1:8102",
    skills=["pemdas.mult"],
    raw={
        "accepts": ["a2a.request:v1"],          # now: envelope
        "produces": ["a2a.response:v1"],        # now: envelope
        "message_types": ["pemdas.mult:v1"],    # what payload types this agent handles
    },
    card_sha256="",
)

SELF_ENDPOINT = make_endpoint(name=CARD.name, version=CARD.version, url=CARD.url, skill="pemdas.mult")


def mult_brain(text: str) -> Dict[str, Any]:
    # 1) Parse request envelope
    req = strict_json_loads(text)

    # 2) Validate envelope + payload schema
    validate_envelope_and_payload(req, kind="request")

    if req["message_type"] != "pemdas.mult:v1":
        raise ValueError(f"MULT cannot handle message_type={req['message_type']}")

    # 3) Extract typed payload
    p = req["payload"]

    a = rat_to_frac(p["a"])   # -> Fraction, reduced
    b = rat_to_frac(p["b"])   # -> Fraction, reduced

    result = a * b            # -> Fraction, reduced

    # 4) Build response payload (project-specific)
    payload = {
        "ok": True,
        "type": "pemdas.result:v1",
        "op": "mult",
        "inputs": {"a": p["a"], "b": p["b"]},   # keep original rat:v2 dicts
        "result": frac_to_rat(result),          # rat:v2 dict
    }
    payload = to_wire(payload)

    # 5) Wrap in response envelope
    dest = req["source"]  # respond back to caller
    resp = make_response(
        req=req,
        message_type="pemdas.result:v1",
        source=SELF_ENDPOINT,
        dest=dest,
        ok=True,
        payload=payload,
    )

    # 6) Validate response envelope + payload schema (optional but nice)
    validate_envelope_and_payload(resp, kind="response")

    # 7) Return as task_result.meta (your server returns task_result under JSON-RPC result)
    return build_task_result(
        artifact_name="pemdas.mult.result",
        parts=[{"type": "text", "text": json.dumps(resp)}],  # optional receipt
        meta=resp,
    )


app = create_a2a_app(CARD, mult_brain)
