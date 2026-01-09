# generalist_agent.py
from __future__ import annotations
from typing import Any, Dict
import time

from openai import OpenAI
from .a2a_core import AgentCard
from .a2a_server import create_a2a_app, build_task_result

AGENT_NAME = "generalist"
AGENT_VERSION = "0.1.0"
AGENT_URL = "http://127.0.0.1:8100"

MODEL = "gpt-4o-mini"

SYSTEM_GENERALIST = (
    "You are a general-purpose assistant.\n"
    "Follow the user's instructions.\n"
    "If asked to output JSON, output JSON.\n"
    "Do not use tools."
)

CARD = AgentCard(
    name=AGENT_NAME,
    version=AGENT_VERSION,
    url=AGENT_URL,
    skills=["general.chat"],
    raw={},
    card_sha256="",  # create_a2a_app can fill this if you want
)

def _call_llm(user_text: str) -> str:
    client = OpenAI()
    resp = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": SYSTEM_GENERALIST},
            {"role": "user", "content": user_text},
        ],
    )
    return (getattr(resp, "output_text", "") or "").strip()

def brain(text: str) -> dict:
    t0 = time.time()
    out = _call_llm(text)

    meta = {
        "agent": AGENT_NAME,
        "agent_version": AGENT_VERSION,
        "model": MODEL,

        # REQUIRED by your client:
        "llm_calls": 1,
        "tools_used": [],
        "schema_validated": False,
        "stub_hit": False,

        # Nice to have:
        "latency_ms": int((time.time() - t0) * 1000),
    }
    parts = [{"kind": "text", "text": out}]
    return build_task_result(
        artifact_name="answer.txt",
        parts=parts,
        meta=meta,
    )

app = create_a2a_app(CARD, brain)
