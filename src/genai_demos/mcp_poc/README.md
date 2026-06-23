# MCP Proof-of-Concept Package

This package contains a small MCP demo for a retail support scenario.
It is designed to be imported from notebooks or lightweight demo scripts.

## Contents

- `server.py` — a local MCP server exposing customer, inventory, ticket, and email tools.
- `mcp_helpers.py` — notebook-friendly helpers for launching a stdio MCP session.
- `router.py` — a constrained router that maps natural-language requests to approved workflows.
- `workflows.py` — deterministic workflows that execute MCP tool calls through a session.

## How to use

1. Run from the repository root so `src/` is available on the import path.
2. In notebooks, either update `sys.path` to include the repo `src/` directory, or install the package in editable mode.

Example notebook import pattern:

```python
import sys
from pathlib import Path

workspace_root = Path.cwd().resolve()
for _ in range(5):
    if (workspace_root / "src").exists():
        break
    workspace_root = workspace_root.parent
sys.path.insert(0, str(workspace_root / "src"))

from genai_demos.mcp_poc.mcp_helpers import with_mcp_session, print_json
from genai_demos.mcp_poc.router import route_with_llm
from genai_demos.mcp_poc.workflows import WORKFLOW_REGISTRY
```

## Notes

- The package is intentionally simple and uses stub data for demo purposes.
- `docs/mcp_poc.md` contains the public-facing explanation and notebook structure.
- The notebooks in `notebooks/mcp/` demonstrate a conceptual introduction and a controlled agentic workflow.
