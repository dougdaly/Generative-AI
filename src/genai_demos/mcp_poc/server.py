"""Demo MCP server for retail support capabilities.

This server exposes stub customer, inventory, ticket, and email tools over MCP.
It is intended for notebook-driven demos and local proof-of-concept use.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Retail Support Demo MCP Server")
server_path = Path(__file__).resolve()

CUSTOMERS: dict[str, dict[str, Any]] = {
    "123": {
        "customer_id": "123",
        "name": "Alex Rivera",
        "email": "alex.rivera@example.com",
        "segment": "student gamer",
        "preferences": ["portable", "gaming", "under $1500", "good battery life"],
        "recent_purchases": ["USB-C dock", "wireless mouse"],
    },
    "456": {
        "customer_id": "456",
        "name": "Priya Shah",
        "email": "priya.shah@example.com",
        "segment": "home office",
        "preferences": ["large monitor", "quiet keyboard", "ergonomic setup"],
        "recent_purchases": ["standing desk"],
    },
}

INVENTORY: list[dict[str, Any]] = [
    {
        "sku": "LAP-100",
        "name": "Falcon 14 Gaming Laptop",
        "category": "laptops",
        "price": 1399,
        "tags": ["gaming", "portable", "student"],
        "in_stock": True,
    },
    {
        "sku": "LAP-200",
        "name": "Canyon 16 Creator Laptop",
        "category": "laptops",
        "price": 1899,
        "tags": ["creator", "large screen", "performance"],
        "in_stock": True,
    },
    {
        "sku": "MON-300",
        "name": "Vista 27 4K Monitor",
        "category": "monitors",
        "price": 399,
        "tags": ["home office", "large monitor", "4k"],
        "in_stock": True,
    },
    {
        "sku": "ACC-400",
        "name": "QuietType Mechanical Keyboard",
        "category": "accessories",
        "price": 129,
        "tags": ["quiet keyboard", "home office"],
        "in_stock": False,
    },
]

TICKET_LOG: list[dict[str, Any]] = []
EMAIL_LOG: list[dict[str, Any]] = []


def _as_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


@mcp.resource("customer://all")
def customer_all() -> str:
    return json.dumps(CUSTOMERS, indent=2)


def _get_inventory_categories() -> list[str]:
    return sorted({item["category"] for item in INVENTORY})


@mcp.resource("inventory://categories")
def inventory_categories() -> str:
    return json.dumps(_get_inventory_categories(), indent=2)


@mcp.tool()
def lookup_customer(customer_id: str) -> dict[str, Any]:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return {"ok": False, "error": f"No customer found for id {customer_id}"}
    return {"ok": True, "customer": customer}


@mcp.tool()
def lookup_inventory(category: str | None = None, tag: str | None = None) -> dict[str, Any]:
    results = INVENTORY
    if category:
        results = [item for item in results if item["category"].lower() == category.lower()]
    if tag:
        results = [item for item in results if tag.lower() in [t.lower() for t in item["tags"]]]
    return {"ok": True, "count": len(results), "items": results}


@mcp.tool()
def recommend_products(customer_id: str, category: str | None = None) -> dict[str, Any]:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return {"ok": False, "error": f"No customer found for id {customer_id}"}

    preferences = {p.lower() for p in customer["preferences"]}
    candidates = [item for item in INVENTORY if item["in_stock"]]
    if category:
        candidates = [item for item in candidates if item["category"].lower() == category.lower()]

    scored = []
    for item in candidates:
        tags = {t.lower() for t in item["tags"]}
        score = len(preferences.intersection(tags))
        scored.append({**item, "match_score": score})

    scored.sort(key=lambda x: (-x["match_score"], x["price"]))
    return {"ok": True, "customer_id": customer_id, "recommendations": scored[:3]}


@mcp.tool()
def create_support_ticket(customer_id: str, issue: str, priority: str = "normal") -> dict[str, Any]:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return {"ok": False, "error": f"No customer found for id {customer_id}"}

    ticket = {
        "ticket_id": f"TICKET-{len(TICKET_LOG) + 1:04d}",
        "customer_id": customer_id,
        "customer_email": customer["email"],
        "issue": issue,
        "priority": priority,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stub": True,
    }
    TICKET_LOG.append(ticket)
    return {"ok": True, "ticket": ticket}


@mcp.tool()
def send_email(customer_id: str, subject: str, body: str) -> dict[str, Any]:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return {"ok": False, "error": f"No customer found for id {customer_id}"}

    email = {
        "to": customer["email"],
        "subject": subject,
        "body": body,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "stub": True,
    }
    EMAIL_LOG.append(email)
    return {"ok": True, "email": email}


@mcp.tool()
def get_activity_log() -> dict[str, Any]:
    return {"tickets": TICKET_LOG, "emails": EMAIL_LOG}


if __name__ == "__main__":
    mcp.run(transport="stdio")
