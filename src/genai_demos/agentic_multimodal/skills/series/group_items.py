from __future__ import annotations

import hashlib
from typing import Any

from agentic_multimodal.skills.data.wikidata_taxa import (
    load_or_build_animal_pool,
    enrich_animal_items,
)

DEFAULT_ANIMAL_WEIGHTS = {
    "mammal": 0.40,
    "bird": 0.35,
    "reptile": 0.25,
}


def stable_take(items: list[dict[str, Any]], n: int, seed: str) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> str:
        return hashlib.md5((item["qid"] + seed).encode("utf-8")).hexdigest()

    return sorted(items, key=key)[:n]


def weighted_targets(n: int, weights: dict[str, float]) -> dict[str, int]:
    raw = {group: n * weight for group, weight in weights.items()}
    targets = {group: int(value) for group, value in raw.items()}

    remaining = n - sum(targets.values())

    remainders = sorted(
        raw,
        key=lambda group: raw[group] - targets[group],
        reverse=True,
    )

    for group in remainders[:remaining]:
        targets[group] += 1

    return {group: count for group, count in targets.items() if count > 0}


def select_stable_group_mix(
    pool: list[dict[str, Any]],
    *,
    count: int,
    seed: str,
    targets: dict[str, int] | None = None,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    if targets is None:
        targets = weighted_targets(count, weights or DEFAULT_ANIMAL_WEIGHTS)

    picked: list[dict[str, Any]] = []

    for group, group_count in targets.items():
        group_items = [item for item in pool if item.get("group") == group]
        picked.extend(
            stable_take(
                group_items,
                group_count,
                seed=f"{seed}:{group}",
            )
        )

    # Top up before returning, so the caller gets a complete, uniform set.
    if len(picked) < count:
        used_qids = {item["qid"] for item in picked}
        remaining = [
            item
            for item in stable_take(pool, len(pool), seed=f"{seed}:topup")
            if item["qid"] not in used_qids
        ]
        picked.extend(remaining[: count - len(picked)])

    return picked[:count]


def get_group_items(
    registry,
    *,
    item_type: str,
    count: int,
    seed: str,
    force_rebuild: bool = False,
) -> list[dict[str, Any]]:
    key = item_type.lower().strip()

    if key != "animals":
        raise ValueError(
            f"Unsupported item_type={item_type!r}. Currently supported: ['animals']"
        )

    pool = load_or_build_animal_pool(
        registry,
        force_rebuild=force_rebuild,
    )

    picked = select_stable_group_mix(
        pool,
        count=count,
        seed=seed,
    )

    # Enrich only the selected animals.
    items = enrich_animal_items(registry, picked)

    missing_display = [item for item in items if not item.get("display")]
    if missing_display:
        raise RuntimeError(
            f"{len(missing_display)} selected items are missing display names."
        )

    return items