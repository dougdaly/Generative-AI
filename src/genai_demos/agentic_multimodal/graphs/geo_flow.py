from langgraph.graph import StateGraph, START, END
from agentic_multimodal.schemas.artifacts import MapSpec, MapMarker
from agentic_multimodal.skills.gen_map_renderer import render_map
from agentic_multimodal.skills.geo.flight_path import (
    great_circle_waypoints,
    validate_lat_cap,
    route_bbox,
    haversine_miles,
)

import re
LATITUDE_CAP = 70.0  # v1 constraint for flight paths

import re
from agentic_multimodal.schemas.artifacts import MapSpec, MapMarker

# optional: local import for typing
from typing import Tuple, Optional


def _parse_from_to(question: str) -> Tuple[Optional[str], Optional[str]]:
    """
    V1 quick parser.
    Expects phrasing like:
      "show me the flight path from Seattle, WA to London, UK"
    """
    m = re.search(r"\bfrom\s+(.*?)\s+to\s+(.+)$", question, flags=re.IGNORECASE)
    if not m:
        return None, None
    return m.group(1).strip(" ."), m.group(2).strip(" .")


def _retrieve_flight_path(state, key, geo):
    """
    Route-first retrieval.
    Requires geo.geocode_place(label) -> (lat, lon)

    Expects deterministic helpers to exist:
      - great_circle_waypoints
      - validate_lat_cap
      - route_bbox
    """

    question = state.get("question", "")
    origin_label, dest_label = _parse_from_to(question)

    if not origin_label or not dest_label:
        spec = MapSpec(region=key, markers=[], title="Flight path (v1)")
        # You could also set a small hint string on state["answer"] in summarize
        return {**state, "geo_key": key, "countries": [], "spec": spec}

    # Geocode via your existing Wikidata stack
    o_lat, o_lon = geo.geocode_place(origin_label)
    d_lat, d_lon = geo.geocode_place(dest_label)

    # Compute route
    waypoints, dist_miles = great_circle_waypoints(
        (o_lat, o_lon),
        (d_lat, d_lon),
        step_miles=50
    )

    # V1 constraint
    validate_lat_cap(waypoints, lat_cap=70.0)

    # canonical bbox format: (west, south, east, north)
    west, south, east, north = route_bbox(waypoints=waypoints)
    miles = haversine_miles((o_lat, o_lon), (d_lat, d_lon))
    spec = MapSpec(
        region=key,
        title = f"Flight Path: {origin_label} → {dest_label} (~{miles:,.0f} mi)",
        markers=[
            MapMarker(lon=o_lon, lat=o_lat, label=origin_label),
            MapMarker(lon=d_lon, lat=d_lat, label=dest_label),
        ],
        meta={
            "route_waypoints": waypoints,
            "bbox": (west, south, east, north),
            "distance_miles": dist_miles,
            "lat_cap": 70.0,
            "step_miles": 50,
        },
    )
    return {**state, "geo_key": key, "countries": [], "spec": spec}


def build_graph(registry, *, checkpointer=None):
    llm  = registry.llm
    geo  = registry.geo
    render_call = render_map

    def _route(q: str) -> str | None:
        ql = q.lower()
        # Handle flight path requests
        if "flight path" in ql or "great circle" in ql:
            return "flight_path_v1"
        # Handle country flags/maps requests
        else:
            if "europe" in ql and "flag" in ql: 
                return "europe_countries_flags"
            if "us" in ql and "state" in ql and "flag" in ql: 
                return "us_states_flags"
            if ("canada" in ql or "canadian" in ql) and ("province" in ql or "territor" in ql) and "flag" in ql:
                return "ca_provinces_territories_flags"
        return None

    def retrieve(state):
        key = state.get("geo_key") or _route(state["question"])
        # -------- flight path --------
        if key == "flight_path_v1":
            return _retrieve_flight_path(state, key, geo)
        # -------- flags/maps --------
        else:
            countries = geo.run(key) if key else []
            markers = []
            for c in countries:
                if not c.capital_coords:
                    continue
                lon, lat = c.capital_coords
                markers.append(MapMarker(
                    lon=lon, lat=lat, label=c.name,
                    image=None,
                    meta={"flag_svg_url": c.flag_svg_url, "capital_name": c.capital_name},
                ))
            spec = MapSpec(region=key or "unknown", markers=markers, title=f"Map: {key}")
            return {**state, "geo_key": key, "countries": countries, "spec": spec}

    def summarize(state):
        # For flight paths, keep this short and factual.
        if state.get("geo_key") == "flight_path_v1":
            out = llm.invoke("Write one short sentence describing a great-circle flight path map.")
            return {**state, "answer": getattr(out, "content", str(out))}

        names = [c.name for c in state.get("countries", [])][:12]
        listed = ", ".join(names) + ("…" if len(state.get("countries", [])) > 12 else "")
        out = llm.invoke(f"Write one short sentence describing this map list: {listed}")
        return {**state, "answer": getattr(out, "content", str(out))}

    def render(state):
        spec = state["spec"]
        key = state.get("geo_key") or getattr(spec, "region", "")

        if key == "flight_path_v1":
            img_path = registry.render.map(
                spec,
                outdir="artifacts/maps",
                size=(2200, 1320),
                marker_px=18,          # smaller for endpoints
                show_labels=True,
                show_country_names=False,
                show_pick_images=False,
                show_flag_markers=False,
                fill_countries=True, 
            )
        else:
            img_path = registry.render.map(spec, outdir="artifacts/maps")

        return {**state, "artifact": spec, "artifact_path": img_path}


    sg = StateGraph(dict)
    sg.add_node("retrieve", retrieve)
    sg.add_node("summarize", summarize)
    sg.add_node("render", render)
    sg.add_edge(START, "retrieve")
    sg.add_edge("retrieve", "summarize")
    sg.add_edge("summarize", "render")
    sg.add_edge("render", END)
    return sg.compile(checkpointer=checkpointer)
