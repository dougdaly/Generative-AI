from __future__ import annotations

from pathlib import Path
import math

from agentic_multimodal.schemas.artifacts import PosterItem, PosterSpec
from agentic_multimodal.skills.adapters.people_to_poster import _asset_from_path


ANIMAL_NEGATIVE_PROMPT = (
    "text, letters, watermark, logo, caption, typography, "
    "frame, border, matting, photo frame, picture frame, "
    "clothing, shirt, suit, tie, collar, dress, buttons, "
    "human, person, hands, arms, mannequin"
)



def animal_prompt(display: str, scientific: str | None, group: str | None) -> str:
    tag = (
        f"{display} ({scientific})"
        if scientific and scientific.lower() != display.lower()
        else display
    )

    group_hint = {
        "bird": "feathers, beak, wings",
        "reptile": "scales, reptile skin texture",
        "mammal": "fur, whiskers",
        "fish": "fins, scales, aquatic animal",
        "insect": "insect body, wings or legs, antennae",
        "amphibian": "smooth skin, amphibian body",
    }.get(group or "", "")

    return (
        f"Wildlife photograph of {tag}. "
        "EXACTLY ONE ANIMAL. Single subject only. One instance only. "
        "Centered, full body visible, sharp focus. "
        f"{group_hint}. "
        "No other animals. No duplicate subjects. No repetition."
    )


def group_items_to_image_picks(items: list[dict]) -> list[dict]:
    picks = []

    for item in items:
        picks.append(
            {
                "qid": item["qid"],
                "name": item["display"],
                "prompt": animal_prompt(
                    item["display"],
                    item.get("scientific"),
                    item.get("group"),
                ),
                "ref_url": item.get("image_url"),
            }
        )

    return picks

def group_items_to_posterspec(
    items: list[dict],
    image_paths: list[str],
    *,
    title: str,
    grid_cols: int | None = None,
) -> PosterSpec:
    if len(items) != len(image_paths):
        raise ValueError(
            f"items and image_paths must have the same length. "
            f"Got {len(items)} items and {len(image_paths)} image paths."
        )

    if grid_cols is None:
        grid_cols = int(math.ceil(math.sqrt(len(items))))

    poster_items = [
        PosterItem(
            image=_asset_from_path(path),
            label=item["display"],
        )
        for item, path in zip(items, image_paths)
    ]

    return PosterSpec(
        title=title,
        grid_cols=grid_cols,
        items=poster_items,
    )