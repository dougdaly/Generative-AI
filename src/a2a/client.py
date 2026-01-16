from __future__ import annotations

import json
from typing import Any, Dict, Optional
import httpx

from .envelope import make_request, make_response, make_endpoint
from .validate import validate_envelope_and_payload

def a2a_send(base_url: str, *, req_id: str, msg_obj: dict, timeout_s: float = 10.0) -> dict:
    url = base_url.rstrip("/") + "/a2a"
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "message/send",
        "params": {"message": {"content": json.dumps(msg_obj)}},
    }

    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, json=payload)

    # Always try to parse the body; your server now returns JSON-RPC errors
    body_text = r.text
    try:
        out = r.json()
    except Exception:
        # If it’s not JSON, include raw body to debug
        raise RuntimeError(f"A2A non-JSON response url={url} status={r.status_code}: {body_text[:2000]}")

    if "error" in out:
        raise RuntimeError(f"A2A error url={url} id={req_id}: {out['error'].get('message')}")

    if "result" not in out:
        raise RuntimeError(f"A2A malformed response url={url} status={r.status_code}: {out}")

    return out["result"]


def a2a_call(
    *,
    dest_base_url: str,
    message_type: str,
    payload: Dict[str, Any],
    source: Dict[str, Any],
    dest: Dict[str, Any],
    trace_id: Optional[str] = None,
    timeout_s: float = 10.0,
) -> Dict[str, Any]:
    """High-level helper: build + validate request envelope, send it, validate response envelope.

    Expects the remote agent to put its response envelope in task_result["meta"].
    Returns the response envelope dict.
    """
    req_env = make_request(
        message_type=message_type,
        payload=payload,
        source=source,
        dest=dest,
        trace_id=trace_id,
    )
    validate_envelope_and_payload(req_env, kind="request")

    task = a2a_send(dest_base_url, req_id=req_env["request_id"], msg_obj=req_env, timeout_s=timeout_s)
    meta = task.get("meta")
    if not isinstance(meta, dict):
        raise ValueError(f"Expected task_result.meta to be a response envelope dict; got: {type(meta).__name__}")

    validate_envelope_and_payload(meta, kind="response")
    if meta.get("ok") is not True:
        raise RuntimeError(f"A2A call failed: {meta.get('error')}")
    return meta
