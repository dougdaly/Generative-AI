"""Deterministic workflows used by the MCP proof-of-concept demo."""

from __future__ import annotations

from typing import Any

from mcp import ClientSession

from .mcp_helpers import call_tool


async def product_recommendation_workflow(
    session: ClientSession,
    customer_id: str,
    category: str,
) -> dict[str, Any]:
    print("STEP 1: Look up customer")
    customer_response = await call_tool(
        session,
        "lookup_customer",
        customer_id=customer_id,
    )

    customer = customer_response["customer"]

    print("\nSTEP 2: Look up inventory")
    inventory_response = await call_tool(
        session,
        "lookup_inventory",
        category=category,
    )

    available_items = [
        item
        for item in inventory_response["items"]
        if item.get("in_stock")
    ]

    if not available_items:
        selected_item = None
        subject = f"No {category} currently available"
        body = (
            f"Hello {customer['name']},\n\n"
            f"We checked current {category} inventory, but nothing is currently in stock.\n\n"
            "Thank you."
        )
    else:
        selected_item = available_items[0]
        subject = f"Recommended product: {selected_item['name']}"
        body = (
            f"Hello {customer['name']},\n\n"
            f"Based on your preferences, we recommend {selected_item['name']}.\n\n"
            f"Price: ${selected_item['price']}\n"
            f"Why it may fit: {', '.join(selected_item.get('tags', []))}\n\n"
            "Thank you."
        )

    print("\nSTEP 3: Generate recommendation email")
    email_response = await call_tool(
        session,
        "send_email",
        customer_id=customer_id,
        subject=subject,
        body=body,
    )

    return {
        "workflow": "product_recommendation",
        "customer": customer_response,
        "inventory": inventory_response,
        "selected_item": selected_item,
        "email": email_response,
    }


async def support_issue_workflow(
    session: ClientSession,
    customer_id: str,
    issue: str,
) -> dict[str, Any]:
    print("STEP 1: Look up customer")
    customer_response = await call_tool(
        session,
        "lookup_customer",
        customer_id=customer_id,
    )

    customer = customer_response["customer"]

    print("\nSTEP 2: Create support ticket")
    ticket_response = await call_tool(
        session,
        "create_support_ticket",
        customer_id=customer_id,
        issue=issue,
    )

    ticket = ticket_response["ticket"]

    print("\nSTEP 3: Generate follow-up email")
    email_response = await call_tool(
        session,
        "send_email",
        customer_id=customer_id,
        subject=f"Support Ticket {ticket['ticket_id']}",
        body=(
            f"Hello {customer['name']},\n\n"
            "Your support ticket has been created.\n\n"
            f"Issue: {issue}\n"
            f"Ticket ID: {ticket['ticket_id']}\n\n"
            "Thank you."
        ),
    )

    return {
        "workflow": "support_issue",
        "customer": customer_response,
        "ticket": ticket_response,
        "email": email_response,
    }


async def inventory_notification_workflow(
    session: ClientSession,
    customer_id: str,
    category: str,
) -> dict[str, Any]:
    print("STEP 1: Look up inventory")
    inventory_response = await call_tool(
        session,
        "lookup_inventory",
        category=category,
    )

    available_items = [
        item
        for item in inventory_response["items"]
        if item.get("in_stock")
    ]

    if not available_items:
        selected_item = None
        subject = f"No {category} currently available"
        body = f"We checked current {category} inventory, but nothing is currently in stock."
    else:
        selected_item = available_items[0]
        subject = f"{selected_item['name']} is available"
        body = f"Good news: {selected_item['name']} is currently in stock for ${selected_item['price']}."

    print("\nSTEP 2: Send customer email")
    email_response = await call_tool(
        session,
        "send_email",
        customer_id=customer_id,
        subject=subject,
        body=body,
    )

    return {
        "workflow": "inventory_notification",
        "inventory": inventory_response,
        "selected_item": selected_item,
        "email": email_response,
    }


WORKFLOW_REGISTRY = {
    "product_recommendation": product_recommendation_workflow,
    "support_issue": support_issue_workflow,
    "inventory_notification": inventory_notification_workflow,
}
