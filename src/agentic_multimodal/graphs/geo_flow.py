# src/agentic_multimodal/graphs/geo_flow.py
from langgraph.graph import StateGraph, START, END
from agentic_multimodal.schemas.artifacts import MapSpec, MapMarker  # your models

def build_graph(registry, *, checkpointer=None):
    llm  = registry.llm
    geo  = registry.geo

    # Try to load a renderer if you already have one; else no-op.
    render_call = None
    try:
        from agentic_multimodal.skills.gen_map_renderer import render_map  # adapt to your function name
        render_call = render_map
    except Exception:
        render_call = None

    def _route(q: str) -> str | None:
        ql = q.lower()
        if "europe" in ql and "flag" in ql: return "europe_countries_flags"
        if "us" in ql and "state" in ql and "flag" in ql: return "us_states_flags"
        if ("canada" in ql or "canadian" in ql) and ("province" in ql or "territor" in ql) and "flag" in ql:
            return "ca_provinces_territories_flags"
        return None

    def retrieve(state):
        key = state.get("geo_key") or _route(state["question"])
        countries = geo.run(key) if key else []
        # Build a MapSpec; carry flag URLs in marker.meta so renderer can fetch/rasterize.
        markers = []
        for c in countries:
            if not c.capital_coords:
                continue
            lon, lat = c.capital_coords
            markers.append(MapMarker(
                lon=lon, lat=lat, label=c.name,
                image=None,  # let renderer attach image if it wants
                meta={"flag_svg_url": c.flag_svg_url, "capital_name": c.capital_name},
            ))
        spec = MapSpec(region=key or "unknown", markers=markers, title=f"Map: {key}")
        return {**state, "countries": countries, "spec": spec}

    def summarize(state):
        names = [c.name for c in state.get("countries", [])][:12]
        listed = ", ".join(names) + ("…" if len(state.get("countries", [])) > 12 else "")
        out = llm.invoke(f"Write one short sentence describing this map list: {listed}")
        return {**state, "answer": getattr(out, "content", str(out))}

    def render(state):
        spec = state["spec"]
        if render_call:
            try:
                path = render_call(spec)  # expected to set spec.path or return path
                if isinstance(path, str):
                    spec.path = path
            except Exception:
                pass
        return {**state, "artifact": spec}

    sg = StateGraph(dict)
    sg.add_node("retrieve", retrieve)
    sg.add_node("summarize", summarize)
    sg.add_node("render", render)
    sg.add_edge(START, "retrieve")
    sg.add_edge("retrieve", "summarize")
    sg.add_edge("summarize", "render")
    sg.add_edge("render", END)
    return sg.compile(checkpointer=checkpointer)
