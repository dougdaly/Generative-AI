from __future__ import annotations

import traceback
import json, time, uuid, hashlib, os, re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypedDict, Awaitable
from fastapi.encoders import jsonable_encoder
from openai import OpenAI

from fastapi import FastAPI, HTTPException, Request


def strip_json_fences(s: str) -> str:
    if not isinstance(s, str):
        return s
    t = s.strip()

    # Strip ```json ... ``` or ``` ... ```
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return t


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def sha256_json_bytes(obj: Any) -> str:
    b = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b).hexdigest()

def extract_numeric_result(task: Dict[str, Any]) -> float:
    meta = task.get("meta") or {}
    if meta.get("type") != "pemdas.result:v1":
        raise ValueError(f"Unexpected child meta.type: {meta.get('type')}")
    return float(meta["result"])

def extract_user_text(payload: Dict[str, Any]) -> str:
    """
    Accepts content as either:
      - string
      - list of parts like [{"type":"text","text":"..."}]
    """
    params = payload.get("params") or {}
    msg = params.get("message") or {}
    content = msg.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        texts: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            t = item.get("text")
            if isinstance(t, str) and t.strip():
                ty = (item.get("type") or item.get("kind") or "").lower()
                if ty in ("text", "input_text", "output_text", ""):
                    texts.append(t)
        return "\n".join(texts).strip()

    return ""

def build_error_response(req_id: str, message: str, code: int = -32000) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

def build_task_result(*, artifact_name: str, parts: List[Dict[str, Any]], meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "contextId": str(uuid.uuid4()),
        "status": {"state": "completed", "timestamp": utc_now_iso()},
        "artifacts": [
            {
                "artifactId": str(uuid.uuid4()),
                "name": artifact_name,
                "parts": parts,
            }
        ],
        "kind": "task",
        "meta": meta,
    }

@dataclass(frozen=True)
class AgentConfig:
    name: str
    version: str
    host: str
    port: int
    skills: List[str]

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

class AgentReply(TypedDict):
    artifact_name: str
    parts: List[Dict[str, Any]]     # e.g. [{"kind":"text","text":"..." }] or [{"kind":"data","data":{...}}]
    meta: Dict[str, Any]            # include llm_calls, tools_used, schema_validated, stub_hit, etc.

BrainFn = Callable[[str, Dict[str, Any]], Awaitable[AgentReply]]

def create_a2a_app(agent, brain: Callable[[str], Any]) -> FastAPI:
    app = FastAPI(title=agent.name)

    @app.get("/.well-known/agent.json")
    def agent_card() -> Dict[str, Any]:
        raw = {
            "name": agent.name,
            "version": agent.version,
            "url": agent.url,
            "skills": agent.skills,  # list[str] or list[{"id":...}] — be consistent
        }
        # add card_sha256 if you want
        return raw

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "name": agent.name, "version": agent.version}

    @app.post("/a2a")
    async def a2a(request: Request) -> Dict[str, Any]:
        print("=== A2A HANDLER HIT v2026-01-13-1 ===", flush=True)
        req_id = None
        try:
            payload = await request.json()
            req_id = payload.get("id") or str(uuid.uuid4())

            if payload.get("method") != "message/send":
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32601, "message": f"Unsupported method: {payload.get('method')}"}}

            text = extract_user_text(payload)
            if not text:
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32602, "message": "No text found in params.message.content"}}

            # Force JSON encoding here so failures get caught and returned as JSON-RPC error
            task_result = brain(text)
            task_result = jsonable_encoder(task_result)
            return {"jsonrpc": "2.0", "id": req_id, "result": task_result}

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id or "unknown",
                "error": {"code": -32000, "message": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"},
            }
    return app


def safe_output_text(resp) -> str:
    chunks = []
    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for c in getattr(item, "content", []) or []:
            if getattr(c, "type", None) == "output_text":
                t = getattr(c, "text", None)
                if isinstance(t, str) and t.strip():
                    chunks.append(t)
    return "\n".join(chunks).strip()


def run_with_tools(
    *,
    model: str,
    system: str,
    user: str,
    tools: list[dict],
    tool_impl: dict[str, Callable[..., Any]],
    max_rounds: int = 16,
) -> tuple[str, dict]:
    """
    Returns (final_text, meta). Meta includes llm_calls + tools_used.
    """
    client = OpenAI()
    MAX_TOOL_CALLS = 40
    llm_calls = 0
    tool_calls_used = 0
    tools_used: list[str] = []

    input_list: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    for _ in range(max_rounds):
        resp = client.responses.create(model=model, tools=tools, input=input_list)
        llm_calls += 1

        # Carry model outputs forward (important for reasoning + tool state).
        input_list += resp.output  # doc pattern :contentReference[oaicite:2]{index=2}

        saw_tool_call = False
        for item in resp.output:
            if getattr(item, "type", None) != "function_call":
                continue
            else:
                tool_calls_used += 1
                if tool_calls_used > MAX_TOOL_CALLS:
                    raise RuntimeError("Exceeded MAX_TOOL_CALLS; aborting.")
            saw_tool_call = True
            name = item.name
            tools_used.append(name)

            if name not in tool_impl:
                # Return tool output as an error string, but still tie to call_id.
                out = {"error": f"Unknown tool: {name}"}
            else:
                raw_args = getattr(item, "arguments", None)

                # arguments might be a dict already, or a JSON string, or empty
                if isinstance(raw_args, dict):
                    args = raw_args
                elif isinstance(raw_args, str) and raw_args.strip():
                    try:
                        args = json.loads(raw_args)
                    except Exception as e:
                        args = {"_parse_error": f"{type(e).__name__}: {e}", "_raw": raw_args}
                else:
                    args = {}

                try:
                    if name not in tool_impl:
                        out = {"error": f"Unknown tool: {name}", "received_args": args}
                    else:
                        out = tool_impl[name](**args)
                except Exception as e:
                    out = {
                        "error": f"{type(e).__name__}: {e}",
                        "tool": name,
                        "received_args": args,
                        "raw_arguments": raw_args,
                    }

            input_list.append({
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": json.dumps(out),
            })  # doc pattern :contentReference[oaicite:3]{index=3}

        if not saw_tool_call:
            return safe_output_text(resp), {
                "llm_calls": llm_calls,
                "tools_used": tools_used,
                "tools_called": tool_calls_used,
            }

    raise RuntimeError(f"Tool loop exceeded max_rounds={max_rounds}")

