from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

def utc_now_iso() -> str:
    # RFC3339 / ISO8601 with Z
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def make_endpoint(*, name: str, version: str | None = None, url: str | None = None, skill: str | None = None) -> Dict[str, Any]:
    ep: Dict[str, Any] = {"name": name}
    if version is not None:
        ep["version"] = version
    if url is not None:
        ep["url"] = url
    if skill is not None:
        ep["skill"] = skill
    return ep

def make_request(
    *,
    message_type: str,
    payload: Dict[str, Any],
    source: Dict[str, Any],
    dest: Dict[str, Any],
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Build an a2a.request:v1 envelope."""
    return {
        "type": "a2a.request:v1",
        "timestamp": timestamp or utc_now_iso(),
        "request_id": request_id or str(uuid.uuid4()),
        "trace_id": trace_id or str(uuid.uuid4()),
        "message_type": message_type,
        "payload": payload,
        "source": source,
        "dest": dest,
    }

def make_response(
    *,
    req: Dict[str, Any],
    message_type: str,
    source: Dict[str, Any],
    dest: Dict[str, Any],
    ok: bool,
    payload: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Build an a2a.response:v1 envelope.

    - When ok=True, include payload and omit error
    - When ok=False, include error and omit payload
    """
    resp: Dict[str, Any] = {
        "type": "a2a.response:v1",
        "timestamp": timestamp or utc_now_iso(),
        "request_id": req["request_id"],
        "trace_id": req["trace_id"],
        "message_type": message_type,
        "ok": bool(ok),
        "source": source,
        "dest": dest,
    }
    if ok:
        resp["payload"] = payload or {}
    else:
        if not error:
            error = {"code": "ERROR", "message": "Unknown error"}
        resp["error"] = error
    return resp
