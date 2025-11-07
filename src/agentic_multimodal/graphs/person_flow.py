from langgraph.graph import StateGraph, START, END

def build_graph(registry, *, checkpointer=None):
    llm = registry.llm
    series = registry.series  # use dispatcher

    def retrieve(state):
        q = state["question"]
        key = state.get("series_key") or _route(q)
        if not key:
            return {**state, "context": []}
        people = series.run(key)
        # serialize minimal context for the LLM
        ctx_lines = []
        for p in people:
            spans = "; ".join(f"{t.start or '?'}–{t.end or '?'}" for t in p.terms)
            ctx_lines.append(f"{p.name} | {spans}")
        return {**state, "context": ctx_lines}

    def generate(state):
        ctx = "\n".join(state.get("context", []))
        prompt = (
            "Answer using ONLY the provided list.\n"
            f"Q: {state['question']}\n\nList:\n{ctx}\n\nA:"
        )
        out = llm.invoke(prompt)
        return {**state, "answer": getattr(out, "content", str(out))}

    def _route(q: str) -> str | None:
        ql = q.lower()
        if "president" in ql or "potus" in ql: return "potus"
        if "monarch" in ql: return "monarchs_eng_gb_uk"
        if "nobel" in ql and "physic" in ql: return "nobel_physics"
        return None

    sg = StateGraph(dict)
    sg.add_node("retrieve", retrieve)
    sg.add_node("generate", generate)
    sg.add_edge(START, "retrieve")
    sg.add_edge("retrieve", "generate")
    sg.add_edge("generate", END)
    return sg.compile(checkpointer=checkpointer)
