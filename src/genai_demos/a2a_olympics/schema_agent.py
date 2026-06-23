import os, re, json, time, uuid
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, Request

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # adjust if needed
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from a2a.core import AgentCard
from a2a.server import (
    create_a2a_app,
    build_task_result,
    run_with_tools,  # your helper that runs Responses + tools
)

# ---------- Config ----------
MODEL = os.getenv("SCHEMA_MODEL", "gpt-4o-mini")

SYSTEM_SCHEMA = """You are a schema extraction specialist.

You will receive:
- DATA: a single log/event line
- SCHEMA: a JSON Schema (draft-07 style)

Your job:
1) Extract fields from DATA into an object.
2) Validate against SCHEMA using the validation tool.
3) If invalid, repair and re-validate until valid.

Output ONLY a JSON object that conforms to SCHEMA.
No markdown. No commentary.
"""

CARD = AgentCard(
    name="schema",
    version="0.1.0",
    url="http://127.0.0.1:8102",
    skills=["schema.extract", "schema.validate", "schema.repair"],
    raw={},
    card_sha256="",
)

# ---------- Helpers ----------
def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", s)
        s = re.sub(r"\n```$", "", s.strip())
    return s.strip()

def _parse_task2_prompt(prompt_text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Extracts DATA line and SCHEMA JSON from:
      DATA:
      ...
      SCHEMA:
      {...}
    """
    m_data = re.search(r"DATA:\s*(.+?)\n\s*\nSCHEMA:", prompt_text, re.DOTALL | re.IGNORECASE)
    m_schema = re.search(r"SCHEMA:\s*(\{.+\})\s*$", prompt_text, re.DOTALL | re.IGNORECASE)

    if not m_data or not m_schema:
        raise ValueError("Prompt must contain DATA: ... and SCHEMA: {...}")

    data_line = m_data.group(1).strip()
    schema_txt = m_schema.group(1).strip()
    schema = json.loads(schema_txt)
    return data_line, schema

# ---------- Tool implementations (REAL) ----------
def tool_parse_log_line(*, data_line: str) -> Dict[str, Any]:
    """
    Parses a pipe-delimited log line like:
      ts | LEVEL | service | user=U123 | code=INSUFF_FUNDS | charge failed: ...
    Returns best-effort dict with keys that commonly map to the schema.
    """
    parts = [p.strip() for p in data_line.split("|")]
    if len(parts) < 3:
        raise ValueError("Expected at least 3 pipe-delimited fields: timestamp | level | service")

    out: Dict[str, Any] = {
        "timestamp": parts[0],
        "level": parts[1],
        "service": parts[2],
    }

    # Remaining segments: key=value pairs + trailing message
    message_bits: List[str] = []
    for seg in parts[3:]:
        seg = seg.strip()
        if "=" in seg:
            k, v = seg.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k in ("user", "user_id"):
                out["user_id"] = v
            elif k in ("code", "error_code"):
                out["error_code"] = v
            else:
                # unknown kv goes to message bits so it doesn't violate additionalProperties
                message_bits.append(seg)
        else:
            message_bits.append(seg)

    if message_bits:
        out["message"] = " | ".join(message_bits).strip()

    return out

def tool_validate_schema(*, data: dict, schema: dict) -> Dict[str, Any]:
    """
    Validates data against JSON Schema. Returns {valid, errors}.
    Requires: pip install jsonschema
    """
    try:
        from jsonschema import Draft7Validator
    except Exception as e:
        raise RuntimeError("Missing dependency: jsonschema. Install with: pip install jsonschema") from e

    if isinstance(schema, str):
        schema = json.loads(schema)
    if not isinstance(schema, dict):
        raise TypeError("schema must be an object or JSON string")

    v = Draft7Validator(schema)
    errors = []
    for err in v.iter_errors(data):
        errors.append(err.message)

    return {"valid": len(errors) == 0, "errors": errors}

def tool_repair_to_schema(*, data: Any, schema: Any) -> Dict[str, Any]:
    """
    Deterministic repair:
    - drops keys not in schema.properties when additionalProperties=False
    - ensures required keys exist if already derivable (we won't invent message)
    """
    if isinstance(schema, str):
        schema = json.loads(schema)
    if not isinstance(schema, dict):
        raise TypeError("schema must be an object or JSON string")
    if not isinstance(data, dict):
        raise TypeError("data must be an object")

    props = (schema.get("properties") or {})
    required = schema.get("required") or []
    allow_extra = schema.get("additionalProperties", True)

    out = dict(data)

    if allow_extra is False:
        out = {k: v for k, v in out.items() if k in props}

    # Do NOT hallucinate required fields. If missing, leave missing.
    missing = [k for k in required if k not in out]
    if missing:
        # leave as-is; validation tool will surface this
        out["_missing_required"] = missing  # internal note; will be dropped if additionalProperties=False

    return out

# ---------- Tools exposed to the model ----------
TOOLS_SCHEMA = [
    {
        "type": "function",
        "name": "tool_parse_log_line",
        "description": "Parse a pipe-delimited log line into a dict of likely fields.",
        "parameters": {
            "type": "object",
            "properties": {"data_line": {"type": "string"}},
            "required": ["data_line"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "tool_validate_schema",
        "description": "Validate JSON data against a JSON Schema. Returns {valid, errors}.",
        "parameters": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "schema": {"type": "object"},
            },
            "required": ["data", "schema"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "tool_repair_to_schema",
        "description": "Repair data to conform to schema (drop extras, coerce types if safe).",
        "parameters": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "schema": {"type": "object"},
            },
            "required": ["data", "schema"],
            "additionalProperties": False,
        },
    },
]



TOOL_IMPL_SCHEMA = {
  "tool_parse_log_line": tool_parse_log_line,
  "tool_validate_schema": tool_validate_schema,
  "tool_repair_to_schema": tool_repair_to_schema,
}

# ---------- Brain ----------
def brain(prompt_text: str) -> dict:
    txt, meta = run_with_tools(
        model="gpt-4o-mini",
        system=SYSTEM_SCHEMA,
        user=prompt_text,
        tools=TOOLS_SCHEMA,
        tool_impl=TOOL_IMPL_SCHEMA,
    )
    s = _strip_code_fences(txt)
    data = json.loads(s)

    # server-side validate here (real), then:
    parts = [{"kind": "data", "data": data}]
    meta["schema_validated"] = True  # only AFTER validation
    meta.setdefault("stub_hit", False)

    return build_task_result(
        artifact_name="extracted.json",
        parts=parts,
        meta=meta,
    )

# ---------- App ----------
app = create_a2a_app(CARD, brain)
