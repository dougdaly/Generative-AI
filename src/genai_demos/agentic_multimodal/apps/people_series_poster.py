from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_multimodal.apps.result import ArtifactResult
from agentic_multimodal.skills.adapters import (
    assert_series_labels_resolved,
    people_to_series_records,
    series_records_to_posterspec,
)
from agentic_multimodal.skills.assets import resolve_series_image_assets
from agentic_multimodal.skills.image_gen import generate_series_record_images
from agentic_multimodal.skills.series.labels import (
    diagnose_entity_resolution,
    repair_people_labels_and_images,
    unresolved_people_labels,
)


def _validate_current_term(records: list[Any]) -> None:
    """Fail if a current office-holder style series looks stale."""
    open_terms = [
        record
        for record in records
        if record.metadata.get("mode") == "per_term"
        and record.metadata.get("end") in (None, "")
    ]

    if not open_terms:
        raise RuntimeError(
            "This office-holder series has no open-ended current term. "
            "The source/cache may be stale. Refresh the Wikidata cache before rendering."
        )


def run_people_series_poster(
    *,
    reg: Any,
    results_dir: str | Path,
    series_key: str,
    title: str,
    mode: str = "per_term",
    cols: int = 6,
    image_scope: str = "entity",
    cache_policy: str = "reuse_then_source",
    image_size: tuple[int, int] = (512, 768),
    http_timeout: int = 45,
    run_image_generation: bool = False,
    expect_open_current_term: bool = False,
    fail_on_missing_images: bool = True,
    outpath: str | Path | None = None,
    image_dir: str | Path | None = None,
) -> ArtifactResult:
    """Build and render a people-series poster.

    This wraps the notebook workflow:

    provider records
        -> generic QID label/image repair
        -> SeriesRecord rows
        -> keyed image resolution
        -> PosterSpec
        -> poster renderer
        -> ArtifactResult
    """

    results_dir = Path(results_dir)

    image_dir = Path(image_dir) if image_dir else results_dir / "people" / series_key / mode
    outpath = Path(outpath) if outpath else results_dir / "posters" / f"poster_{series_key}_{mode}.webp"

    image_dir.mkdir(parents=True, exist_ok=True)
    outpath.parent.mkdir(parents=True, exist_ok=True)

    people_raw = reg.series.run(series_key)

    people = repair_people_labels_and_images(
        reg.sparql,
        people_raw,
        language="en",
        prefer_live=True,
        strict=True,
    )

    unresolved_people = unresolved_people_labels(people)
    if unresolved_people:
        preview = "\n".join(
            f"- {getattr(person, 'qid', None)}: name={getattr(person, 'name', None)!r}"
            for person in unresolved_people[:20]
        )
        qids = [getattr(person, "qid", None) for person in unresolved_people[:10]]
        diagnostics = diagnose_entity_resolution(reg.sparql, qids, language="en")

        raise RuntimeError(
            "Some Person records still have unresolved display labels after generic QID repair. "
            "Do not render a public poster with raw QIDs.\n"
            + preview
            + "\n\nResolver diagnostics:\n"
            + repr(diagnostics)
        )

    records = people_to_series_records(
        people,
        series_key=series_key,
        mode=mode,
        image_scope=image_scope,
    )

    assert_series_labels_resolved(records)

    if expect_open_current_term and mode == "per_term":
        _validate_current_term(records)

    if run_image_generation:
        generate_series_record_images(
            records,
            outdir=str(image_dir),
            skip_existing=False,
        )

    resolution = resolve_series_image_assets(
        records,
        outdir=image_dir,
        cache_policy=cache_policy,
        size=image_size,
        http_timeout=http_timeout,
    )

    warnings: list[str] = []

    if resolution.missing:
        warnings.extend(f"Missing image for image_key={key}" for key in resolution.missing)

        if fail_on_missing_images:
            raise RuntimeError(
                "Some records do not have resolved images. "
                "Use a placeholder-enabled cache policy only when placeholders are acceptable.\n"
                + "\n".join(resolution.missing[:20])
            )

    spec = series_records_to_posterspec(
        records,
        title=title,
        image_assets=resolution.assets,
        cols=cols,
    )

    rendered_path = Path(reg.render.poster(spec, outpath=str(outpath)))

    return ArtifactResult(
        path=rendered_path,
        kind="people_series_poster",
        title=title,
        spec=spec,
        trace={
            "series_key": series_key,
            "mode": mode,
            "image_scope": image_scope,
            "people_count": len(people),
            "record_count": len(records),
            "unique_image_keys": len({record.image_key for record in records}),
            "image_dir": str(image_dir),
            "manifest_path": str(resolution.manifest_path) if resolution.manifest_path else None,
            "expect_open_current_term": expect_open_current_term,
        },
        cache_hits={
            "image_assets_reused": len(resolution.reused),
        },
        cache_misses={
            "image_assets_downloaded": len(resolution.downloaded),
            "image_placeholders": len(resolution.placeholders),
            "image_missing": len(resolution.missing),
        },
        cache_summary={
            "cache_policy": cache_policy,
            "assets": len(resolution.assets),
            "reused": len(resolution.reused),
            "downloaded": len(resolution.downloaded),
            "placeholders": len(resolution.placeholders),
            "missing": len(resolution.missing),
        },
        warnings=warnings,
    ).require_exists()