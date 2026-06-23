# MCP Proof-of-Concept Demo

This demo package demonstrates a simple MCP-driven retail support scenario.

## Structure

- `notebooks/mcp/01_mcp_intro.ipynb` — conceptual introduction to MCP and why discovery matters.
- `notebooks/mcp/02_mcp_controlled_agentic_workflow.ipynb` — a controlled agentic workflow that routes natural-language requests through an LLM router and executes approved MCP workflows.
- `src/genai_demos/mcp_poc/server.py` — MCP server exposing customer, inventory, ticket, and email tools.
- `src/genai_demos/mcp_poc/router.py` — router logic for selecting approved workflows.
- `src/genai_demos/mcp_poc/mcp_helpers.py` — MCP session helpers for notebook-driven demos.
- `src/genai_demos/mcp_poc/workflows.py` — deterministic workflow implementations for the demo.

## Notes

- The demo uses stub data and a constrained workflow registry to keep the example safe and easy to understand.
- `01_mcp_intro.ipynb` is conceptual and uses local Python examples rather than the full MCP SDK.
- `02_mcp_controlled_agentic_workflow.ipynb` demonstrates a real MCP client/server interaction and an agentic routing layer.
- Import paths are package-relative and target `genai_demos.mcp_poc`.
