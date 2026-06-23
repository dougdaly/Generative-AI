"""MCP helper utilities used by the MCP proof-of-concept notebooks."""

from __future__ import annotations

import json
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .server import server_path, server_path as SERVER_PATH

server_params = StdioServerParameters(
    command=sys.executable,
    args=[str(server_path)],
)


def print_json(data: Any) -> None:
    try:
        print(json.dumps(data, indent=2, default=str))
    except TypeError:
        print(json.dumps(str(data), indent=2))


def tool_result_to_python(result: Any) -> Any:
    if not getattr(result, "content", None):
        return None

    first = result.content[0]
    text = getattr(first, "text", None)
    if text is None:
        return first

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def with_mcp_session(callback: Callable[[ClientSession], Awaitable[Any]]) -> Any:
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await callback(session)


async def call_tool(session: ClientSession, tool_name: str, **kwargs: Any) -> Any:
    result = await session.call_tool(
        tool_name,
        arguments=kwargs,
    )

    parsed = tool_result_to_python(result)
    print_json(parsed)

    return parsed
