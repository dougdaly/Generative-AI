from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_multimodal.apps.result import ArtifactResult
from agentic_multimodal.skills.adapters.items_to_poster import (
    ANIMAL_NEGATIVE_PROMPT,
    group_items_to_image_picks,
    group_items_to_posterspec,
)
from agentic_multimodal.skills.image_gen import batch_generate_subject_images, safe_slug
from agentic_multimodal.skills.series.group_items import get_group_items


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _image_files(directory: str | Path) -> list[str]:
    directory = Path(directory)
    if not directory.exists():
        return []

    return sorted(
        str(path)
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS
    )


def _expected_generated_path(
    *,
    pick: dict[str, Any],
    item_index: int,
    batch_size: int,
    image_dir: Path,
) -> Path | None:
    """Find the expected generated image for one pick.

    `batch_generate_subject_images(...)` calls `generate_prompt_images(...)`
    per batch, and `generate_prompt_images(...)` numbers files from 001 inside
    each batch. So the expected filename is based on the index within the batch,
    not the global item index.
    """

    local_index = ((item_index - 1) % batch_size) + 1
    slug = safe_slug(str(pick["name"]))

    primary = image_dir / f"{local_index:03d}_{slug}.png"
    if primary.exists():
        return primary

    matches = sorted(
        path
        for path in image_dir.glob(f"{local_index:03d}_{slug}.*")
        if path.suffix.lower() in _IMAGE_EXTENSIONS
    )

    return matches[0] if matches else None


def _resolve_cached_animal_paths(
    picks: list[dict[str, Any]],
    *,
    image_dir: Path,
    batch_size: int,
    allow_positional_cache_fallback: bool,
) -> tuple[list[str], list[str], bool]:
    """Resolve cached animal image paths in pick order.

    Returns:
        image_paths, missing_names, used_positional_fallback
    """

    resolved: list[str] = []
    missing: list[str] = []

    for index, pick in enumerate(picks, start=1):
        path = _expected_generated_path(
            pick=pick,
            item_index=index,
            batch_size=batch_size,
            image_dir=image_dir,
        )

        if path is None:
            missing.append(str(pick["name"]))
        else:
            resolved.append(str(path))

    if not missing:
        return resolved, missing, False

    if allow_positional_cache_fallback:
        cached = _image_files(image_dir)
        if len(cached) >= len(picks):
            return cached[: len(picks)], [], True

    return resolved, missing, False


def run_animal_poster(
    *,
    reg: Any,
    results_dir: str | Path,
    animal_count: int = 10,
    animal_seed: str = "animals_mix_v1",
    title: str | None = None,
    selection_mode: str = "grouped_random",
    force_rebuild_items: bool = False,
    run_image_generation: bool = False,
    fail_on_missing_images: bool = True,
    allow_positional_cache_fallback: bool = False,
    image_dir: str | Path | None = None,
    outpath: str | Path | None = None,
    image_size: tuple[int, int] = (512, 512),
    tile_size: tuple[int, int] = (768, 768),
    steps: int = 24,
    cfg: float = 6.0,
    batch_size: int = 5,
    grid_cols: int | None = None,
    skip_existing: bool = True,
    negative_prompt: str = ANIMAL_NEGATIVE_PROMPT,
) -> ArtifactResult:
    """Build and render an animal poster.

    This wraps the notebook workflow:

    grouped animal selector
        -> prompt/image-pick records
        -> optional image generation or keyed filename cache reuse
        -> PosterSpec
        -> shared poster renderer
        -> ArtifactResult
    """

    if animal_count <= 0:
        raise ValueError(f"animal_count must be positive, got {animal_count}")

    results_dir = Path(results_dir)
    title = title or f"{animal_count} Animals"

    image_dir = Path(image_dir) if image_dir else results_dir / f"animals_portraits_{animal_count}"
    outpath = (
        Path(outpath)
        if outpath
        else results_dir / "posters" / f"poster_animals_{animal_count}_mixed.webp"
    )

    image_dir.mkdir(parents=True, exist_ok=True)
    outpath.parent.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []

    items = get_group_items(
        reg,
        item_type="animals",
        count=animal_count,
        seed=animal_seed,
        force_rebuild=force_rebuild_items,
    )

    picks = group_items_to_image_picks(items)

    cached_before = set(_image_files(image_dir))

    if run_image_generation:
        paths = batch_generate_subject_images(
            picks,
            outdir=str(image_dir),
            batch_size=batch_size,
            size=image_size,
            steps=steps,
            cfg=cfg,
            seed=1337,
            skip_existing=skip_existing,
            negative_prompt=negative_prompt,
        )
        missing: list[str] = []
        used_positional_fallback = False
    else:
        paths, missing, used_positional_fallback = _resolve_cached_animal_paths(
            picks,
            image_dir=image_dir,
            batch_size=batch_size,
            allow_positional_cache_fallback=allow_positional_cache_fallback,
        )

    cached_after = set(_image_files(image_dir))
    generated_or_added = sorted(cached_after - cached_before)

    if used_positional_fallback:
        warnings.append(
            "Used positional cache fallback. This is acceptable for migration, "
            "but generated animal images should eventually be resolved by manifest or stable key."
        )

    if missing:
        warnings.extend(f"Missing cached/generated image for {name}" for name in missing)

        if fail_on_missing_images:
            raise RuntimeError(
                "Not enough animal images were available to render the poster. "
                "Set run_image_generation=True, warm the cache, or intentionally enable "
                "allow_positional_cache_fallback for old caches.\n"
                + "\n".join(missing[:20])
            )

    if len(paths) < len(items):
        raise RuntimeError(
            f"Need {len(items)} image paths to render, but only resolved {len(paths)}."
        )

    spec = group_items_to_posterspec(
        items,
        image_paths=paths[: len(items)],
        title=title,
        grid_cols=grid_cols,
    )

    rendered_path = Path(
        reg.render.poster(
            spec,
            outpath=str(outpath),
            tile_size=tile_size,
        )
    )

    group_counts = {
        group: sum(1 for item in items if item.get("group") == group)
        for group in sorted({item.get("group") for item in items})
    }

    return ArtifactResult(
        path=rendered_path,
        kind="animal_poster",
        title=title,
        spec=spec,
        trace={
            "animal_count": animal_count,
            "animal_seed": animal_seed,
            "selection_mode": selection_mode,
            "item_count": len(items),
            "image_count": len(paths[: len(items)]),
            "group_counts": group_counts,
            "image_dir": str(image_dir),
            "outpath": str(outpath),
            "run_image_generation": run_image_generation,
            "allow_positional_cache_fallback": allow_positional_cache_fallback,
            "used_positional_cache_fallback": used_positional_fallback,
            "render_settings": {
                "image_size": image_size,
                "tile_size": tile_size,
                "steps": steps,
                "cfg": cfg,
                "batch_size": batch_size,
                "grid_cols": grid_cols,
            },
            "sample_items": [item.get("display") for item in items[:8]],
        },
        cache_hits={
            "resolved_images": len(paths),
            "cached_before": len(cached_before),
        },
        cache_misses={
            "missing_images": len(missing),
            "generated_or_added": len(generated_or_added),
        },
        cache_summary={
            "image_dir": str(image_dir),
            "cached_before": len(cached_before),
            "cached_after": len(cached_after),
            "generated_or_added": len(generated_or_added),
            "resolved": len(paths),
            "missing": len(missing),
            "used_positional_fallback": used_positional_fallback,
        },
        warnings=warnings,
    ).require_exists()