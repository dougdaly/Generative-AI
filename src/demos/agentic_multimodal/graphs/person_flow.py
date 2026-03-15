from langgraph.graph import StateGraph, START, END
from langgraph.graph import StateGraph, START, END

def build_graph(registry, *, checkpointer=None):
    """
    Simple 2-node LangGraph:
      1) retrieve: choose a series key + fetch a fixed list of people
      2) generate: ask the LLM to answer using ONLY that list (no extra knowledge)

    This is intentionally "RAG-lite":
    - Retrieval is deterministic (our own curated series dispatcher).
    - Generation is constrained (LLM only sees a serialized list).
    - Output is text, not images/posters. Poster pipelines live elsewhere.

    Why a StateGraph for only 2 steps?
    - Matches the orchestration pattern used by the rest of the repo.
    - Checkpointing support (resume / inspect intermediate state).
    - Easy to extend later (filters, ranking, citations, formatting, tool calls, etc.)
    """

    llm = registry.llm
    series = registry.series  # "dispatcher" that knows how to run series keys like potus/nobel/etc.

    def retrieve(state):
        """
        Retrieve step:
        - Decide which series to use (explicit series_key or inferred via _route()).
        - Fetch the list of people for that series.
        - Convert it to minimal context lines for the LLM.

        Input state keys used:
          - question: str
          - series_key: optional str (overrides routing)

        Output state keys added:
          - context: list[str] where each line looks like "Name | start–end; start–end"
        """
        q = state["question"]

        # Prefer an explicit series_key (caller knows what they want).
        # Otherwise infer it from the question text.
        key = state.get("series_key") or _route(q)

        # No match means "no retrieval". We return empty context rather than erroring.
        if not key:
            return {**state, "context": []}

        # series.run(key) returns domain objects (likely Person records with terms).
        people = series.run(key)

        # Serialize to plain strings so the LLM has a compact, predictable input format.
        # This avoids leaking irrelevant fields and keeps prompts stable.
        ctx_lines = []
        for p in people:
            # Each person may have multiple terms (e.g., office terms).
            spans = "; ".join(f"{t.start or '?'}–{t.end or '?'}" for t in p.terms)
            ctx_lines.append(f"{p.name} | {spans}")

        return {**state, "context": ctx_lines}

    def generate(state):
        """
        Generate step:
        - Builds a strict prompt: "Answer using ONLY the provided list."
        - Hands the question + list to the LLM.
        - Returns answer as raw text.

        Notes:
        - This is intentionally non-agentic: no tools, no extra retrieval.
        - If context is empty, the LLM may still try to answer. Up to you whether to gate that.
        """
        ctx = "\n".join(state.get("context", []))

        prompt = (
            "Answer using ONLY the provided list.\n"
            f"Q: {state['question']}\n\n"
            f"List:\n{ctx}\n\n"
            "A:"
        )

        out = llm.invoke(prompt)

        # Some LLM wrappers return an object with .content, some return raw strings.
        return {**state, "answer": getattr(out, "content", str(out))}

    def _route(q: str) -> str | None:
        """
        Very small router: maps a natural language question to a known series key.

        Keep this dumb on purpose.
        If routing gets complex, move to:
          - a registry of routes in YAML
          - an LLM router
          - or a dedicated intent parser node

        Returns:
          - a series key string understood by registry.series.run()
          - or None if no route matches
        """
        ql = q.lower()
        if "president" in ql or "potus" in ql:
            return "potus"
        if "monarch" in ql:
            return "monarchs_eng_gb_uk"
        if "nobel" in ql and "physic" in ql:
            return "nobel_physics"
        return None

    # Build and wire the graph: START -> retrieve -> generate -> END
    # LangGraph state is just a dict passed between nodes.
    sg = StateGraph(dict)
    sg.add_node("retrieve", retrieve)
    sg.add_node("generate", generate)
    sg.add_edge(START, "retrieve")
    sg.add_edge("retrieve", "generate")
    sg.add_edge("generate", END)

    # checkpointer enables persistence/debugging/resume across runs
    return sg.compile(checkpointer=checkpointer)
