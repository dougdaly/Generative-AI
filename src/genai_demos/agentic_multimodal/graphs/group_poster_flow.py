from __future__ import annotations

import re
from typing import Optional, Tuple

from langgraph.graph import StateGraph, START, END
from agentic_multimodal.schemas.artifacts import PosterSpec

from agentic_multimodal.skills.series.group_items import get_group_items
from agentic_multimodal.skills.adapters.items_to_poster import group_items_to_posterspec


_RE_GROUP = re.compile(
    r"(?:poster|group)\D*(\d{1,4})\s+(animals?|plants?|flowers?)\b",
    flags=re.IGNORECASE,
)

def _parse_count_type(question: str) -> Tuple[Optional[int], Optional[str]]:
    if not question:
        return None, None
    m = _RE_GROUP.search(question)
    if not m:
        return None, None

    count = int(m.group(1))
    raw = m.group(2).lower()

    if raw.startswith("animal"):
        return count, "animals"
    if raw.startswith("plant"):
        return count, "plants"
    if raw.startswith("flower"):
        return count, "flowers"
    return None, None


def build_graph(registry, *, checkpointer=None):
    llm = registry.llm

    def _route(q: str) -> str | None:
        cnt, typ = _parse_count_type(q or "")
        return "group_poster_v1" if (cnt and typ) else None

    def retrieve(state):
        q = state.get("question", "")

        poster_key = state.get("poster_key") or _route(q)
        if not poster_key:
            empty = PosterSpec(title="Group Poster (v1)", grid_cols=1, items=[])
            return {**state, "poster_key": None, "items": [], "spec": empty}

        item_type = state.get("item_type")
        count = state.get("count")

        if not item_type or not count:
            parsed_count, parsed_type = _parse_count_type(q)
            item_type = item_type or parsed_type
            count = count or parsed_count

        item_type = item_type or "animals"
        count = int(count or 100)
        seed = str(state.get("seed", "seed42"))

        items = get_group_items(registry, item_type=item_type, count=count, seed=seed)

        return {
            **state,
            "poster_key": poster_key,
            "item_type": item_type,
            "count": count,
            "items": items,
        }

    def generate(state):
        items = state.get("items", [])
        if not items:
            empty = PosterSpec(title="Group Poster (v1)", grid_cols=1, items=[])
            return {**state, "image_paths": [], "spec": empty}

        item_type = state.get("item_type", "animals")
        cols = int(state.get("cols", 10))
        style = state.get("style", "photo")

        picks = []
        for it in items:
            prompt = registry.image_prompts.subject_portrait(
                subject_type=item_type,
                name=it.name,
                style=style,
                no_text=True,
            )
            picks.append({"qid": it.qid, "name": it.name, "prompt": prompt})

        image_paths = registry.image_gen.batch_generate(picks)

        title = state.get("title") or f"{len(items)} {item_type.title()}"
        spec = group_items_to_posterspec(items, title=title, image_paths=image_paths, cols=cols)

        return {**state, "picks": picks, "image_paths": image_paths, "spec": spec}

    def summarize(state):
        item_type = state.get("item_type", "items")
        items = state.get("items", [])
        names = [it.name for it in items][:12]
        listed = ", ".join(names) + ("…" if len(items) > 12 else "")
        out = llm.invoke(f"Write one short sentence describing a poster of {len(items)} {item_type}: {listed}")
        return {**state, "answer": getattr(out, "content", str(out))}

    def render(state):
        spec = state["spec"]

        # Your registry exposes render.poster=compose_poster_spec
        # This should return an output image path similar to render_map.
        out_path = registry.render.poster(spec, outdir="artifacts/posters")

        return {**state, "artifact": spec, "artifact_path": out_path}

    sg = StateGraph(dict)
    sg.add_node("retrieve", retrieve)
    sg.add_node("generate", generate)
    sg.add_node("summarize", summarize)
    sg.add_node("render", render)

    sg.add_edge(START, "retrieve")
    sg.add_edge("retrieve", "generate")
    sg.add_edge("generate", "summarize")
    sg.add_edge("summarize", "render")
    sg.add_edge("render", END)

    return sg.compile(checkpointer=checkpointer)
