from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Literal, Optional
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

try:
    import jsonschema
except Exception as e:  # pragma: no cover
    jsonschema = None  # type: ignore

SchemaKind = Literal["request", "response"]

CONTRACTS_DIR = Path(__file__).resolve().parent / "contracts"
_SCHEMA_CACHE: dict[str, dict] = {}

def schema_filename_from_message_type(message_type: str) -> str:
    # e.g. "pemdas.add:v1" -> "pemdas_add_v1.json"
    return message_type.replace(".", "_").replace(":", "_") + ".json"

def _load_schema_file(filename: str) -> Dict[str, Any]:
    if filename in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[filename]
    path = CONTRACTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    _SCHEMA_CACHE[filename] = schema
    return schema



def _build_registry() -> Registry:
    reg = Registry()
    for p in CONTRACTS_DIR.glob("*.json"):
        schema = json.loads(p.read_text())
        sid = schema.get("$id")
        if not sid:
            raise ValueError(f"Schema missing $id: {p}")
        reg = reg.with_resource(sid, Resource.from_contents(schema))
    return reg


_REGISTRY = _build_registry()


def validate_json(schema: dict, instance: object, *, where: str) -> None:
    v = Draft202012Validator(schema, registry=_REGISTRY)
    errors = sorted(v.iter_errors(instance), key=lambda e: e.json_path)
    if errors:
        e = errors[0]
        raise ValueError(f"Schema validation failed at {where}: {e.message}") from e

def validate_envelope_and_payload(obj: Dict[str, Any], *, kind: SchemaKind) -> None:
    """Validate an A2A envelope and its payload.

    Requires these schema files in src/a2a/contracts/:
      - a2a_request_v1.json
      - a2a_response_v1.json
      - <message_type translated to filename> (payload schema), e.g. pemdas_add_v1.json

    For responses:
      - If ok=True, payload is validated against message_type schema.
      - If ok=False, payload is not expected (envelope schema enforces error).
    """
    if kind == "request":
        env = _load_schema_file("a2a_request_v1.json")
        validate_json(env, obj, where="a2a.request:v1")
        payload_schema = _load_schema_file(schema_filename_from_message_type(obj["message_type"]))
        validate_json(payload_schema, obj["payload"], where=f"payload:{obj['message_type']}")
        return

    if kind == "response":
        env = _load_schema_file("a2a_response_v1.json")
        validate_json(env, obj, where="a2a.response:v1")
        if obj.get("ok") is True:
            payload_schema = _load_schema_file(schema_filename_from_message_type(obj["message_type"]))
            validate_json(payload_schema, obj.get("payload"), where=f"payload:{obj['message_type']}")
        return

    raise ValueError(f"Unsupported kind: {kind}")
