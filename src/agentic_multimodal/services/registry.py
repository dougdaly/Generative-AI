# src/agentic_multimodal/services/registry.py
from typing import Protocol, Any, Dict

class Tool(Protocol):
    name: str
    async def run(self, **kwargs) -> Any: ...

class Registry:
    def __init__(self) -> None:
        self.tools: Dict[str, Tool] = {}
    def register(self, tool: Tool) -> None:
        if getattr(tool, "name", None) is None:
            raise ValueError("Tool must define .name")
        self.tools[tool.name] = tool
    def get(self, name: str) -> Tool:
        if name not in self.tools:
            raise KeyError(f"Tool not registered: {name}")
        return self.tools[name]

