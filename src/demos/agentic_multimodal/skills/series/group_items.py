from __future__ import annotations
from agentic_multimodal.skills.data.wikipedia_category_members import fetch_from_categories, NamedItem

CATEGORY_SETS = {
    "animals": [
        "Category:Mammals",
        "Category:Birds",
        "Category:Reptiles",
        "Category:Amphibians",
        "Category:Fish",
        "Category:Insects",
    ],
    "plants": [
        "Category:Plants",
    ],
    "flowers": [
        "Category:Flowers",
    ],
}

def get_group_items(registry, *, item_type: str, count: int, seed: str) -> list[NamedItem]:
    key = item_type.lower().strip()
    if key not in CATEGORY_SETS:
        raise ValueError(f"Unsupported item_type={item_type!r}. Expected {sorted(CATEGORY_SETS)}")

    return fetch_from_categories(
        registry,
        categories=CATEGORY_SETS[key],
        count=count,
        seed=seed,
        pool_per_cat=max(200, count * 3),
    )
