# skills/adapters/items_to_poster.py
from __future__ import annotations
from typing import Iterable

from agentic_multimodal.schemas.artifacts import PosterItem, PosterSpec
from agentic_multimodal.skills.adapters.people_to_poster import _asset_from_path
from agentic_multimodal.skills.data.wikidata_taxa import NamedItem


def items_to_posterspec(
    items: list[NamedItem],
    *,
    title: str,
    image_paths: Iterable[str],
    cols: int = 10,
) -> PosterSpec:
    poster_items: list[PosterItem] = []
    for it, path in zip(items, image_paths):
        poster_items.append(PosterItem(image=_asset_from_path(path), label=it.name))
    return PosterSpec(title=title, grid_cols=cols, items=poster_items)
