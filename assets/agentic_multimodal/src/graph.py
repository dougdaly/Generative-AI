from langgraph.graph import StateGraph, END
from typing import TypedDict

class PipelineState(TypedDict):
    user_request: str
    research: dict      # Presidents/Capitals
    images: dict        # {key: local_path}
    artifact: str       # final PNG/PDF path

from agents.research import research_node
from agents.image_gen import image_node
from agents.compositor import compose_node

def build_graph():
    g = StateGraph(PipelineState)
    g.add_node("research", research_node)
    g.add_node("images", image_node)
    g.add_node("compose", compose_node)
    g.set_entry_point("research")
    g.add_edge("research", "images")
    g.add_edge("images", "compose")
    g.add_edge("compose", END)
    return g.compile()
