"""Small LLM router for MCP workflow demo."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

ALLOWED_WORKFLOWS = {
    "product_recommendation",
    "support_issue",
    "inventory_notification",
}

ROUTER_SYSTEM_PROMPT = """You route user requests to one approved workflow.

Allowed workflows:

1. product_recommendation
Use when the user asks for a product recommendation for a customer.
Required parameters:
- customer_id
- category

2. support_issue
Use when the user reports a customer support issue.
Required parameters:
- customer_id
- issue

3. inventory_notification
Use when the user asks to notify a customer about product availability.
Required parameters:
- customer_id
- category

Return ONLY valid JSON. No markdown fences.

JSON shape:
{
  "workflow": "product_recommendation | support_issue | inventory_notification",
  "parameters": {
    "customer_id": "...",
    "category": "...",
    "issue": "..."
  }
}

Use these defaults if missing:
- customer_id: "123"
- category: "laptops"
"""


def parse_json_from_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned.strip(), flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned.strip()).strip()
    return json.loads(cleaned)


def route_with_rules(user_prompt: str) -> dict[str, Any]:
    text = user_prompt.lower()

    customer_id_match = re.search(r"\bcustomer\s+(\d+)\b", text)
    customer_id = customer_id_match.group(1) if customer_id_match else "123"

    if "monitor" in text:
        category = "monitors"
    elif "keyboard" in text or "accessor" in text:
        category = "accessories"
    else:
        category = "laptops"

    if any(word in text for word in ["broken", "issue", "problem", "support", "ticket", "overheating"]):
        return {
            "workflow": "support_issue",
            "parameters": {
                "customer_id": customer_id,
                "issue": user_prompt,
            },
        }

    if any(word in text for word in ["notify", "email", "available", "availability", "in stock"]):
        return {
            "workflow": "inventory_notification",
            "parameters": {
                "customer_id": customer_id,
                "category": category,
            },
        }

    return {
        "workflow": "product_recommendation",
        "parameters": {
            "customer_id": customer_id,
            "category": category,
        },
    }


def route_with_llm(user_prompt: str, model: str = "gpt-4.1-mini") -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        print("STUB: OPENAI_API_KEY not found. Using deterministic fallback router.")
        return route_with_rules(user_prompt)

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content or ""
    route = parse_json_from_text(content)

    workflow = route.get("workflow")
    if workflow not in ALLOWED_WORKFLOWS:
        raise ValueError(f"Unknown workflow selected by router: {workflow}")

    route.setdefault("parameters", {})
    route["parameters"].setdefault("customer_id", "123")

    if workflow in {"product_recommendation", "inventory_notification"}:
        route["parameters"].setdefault("category", "laptops")

    if workflow == "support_issue":
        route["parameters"].setdefault("issue", user_prompt)

    return route
