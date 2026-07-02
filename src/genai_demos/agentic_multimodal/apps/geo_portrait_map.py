from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_multimodal.apps.result import ArtifactResult
from agentic_multimodal.skills.data.wikimedia_cache import (
    attach_flag_paths_to_mapspec,
    cache_flags_for_markers,
)


def _sort_countries_for_people_map(countries: list[Any], n_countries: int) -> list[Any]:
    """Prefer larger-population countries for the optional people map."""
    return sorted(
        countries,
        key=lambda country: getattr(country, "population", None) or 0,
        reverse=True,
    )[:n_countries]


def _subject_type_for_portrait_type(portrait_type: str) -> str:
    """Translate selector category into portrait-rendering subject type."""
    if portrait_type == "musicians":
        return "musicians"
    if portrait_type in {"sports", "sportsperson", "athletes"}:
        return "sportsperson"
    return portrait_type


def run_geo_portrait_map(
    *,
    reg: Any,
    results_dir: str | Path,
    region_key: str,
    title: str,
    marker_mode: str = "flags",  # "flags" | "people"
    map_region: str | None = None,
    map_outdir: str | Path | None = None,
    flag_cache_dir: str | Path | None = None,
    allow_live_flag_fetch: bool = True,
    flag_width: int = 128,
    flag_timeout: float = 10.0,
    flag_retries: int = 2,
    portrait_type: str = "sports",
    n_countries: int = 15,
    min_population: int | None = None,
    limit_candidates: int = 60,
    pageview_days: int = 90,
    score: str = "blended",
    portrait_dir: str | Path | None = None,
    size: tuple[int, int] = (2200, 1320),
    marker_px: int = 42,
    flag_marker_size_px: int = 42,
    pick_image_size_px: int = 56,
    show_labels: bool = True,
    show_country_names: bool = False,
    show_capital_names: bool = False,
    show_pick_images: bool = False,
    show_flag_markers: bool = True,
    show_fallback_dots: bool = True,
    min_flag_separation_px: int = 0,
    allow_live_image_fetch: bool = False,
    extra_render_kwargs: dict[str, Any] | None = None,
) -> ArtifactResult:
    """Build and render a geographic flag or portrait map.

    This wraps the notebook workflow:

    geographic provider
        -> country/subdivision rows
        -> optional per-country person selection
        -> MapSpec
        -> flag or portrait asset resolution
        -> deterministic map renderer
        -> ArtifactResult
    """

    if marker_mode not in {"flags", "people"}:
        raise ValueError(f"marker_mode must be 'flags' or 'people', got {marker_mode!r}")

    results_dir = Path(results_dir)
    map_outdir = Path(map_outdir) if map_outdir else results_dir / "maps"
    flag_cache_dir = Path(flag_cache_dir) if flag_cache_dir else results_dir / "cache" / "wikimedia" / "flags"
    portrait_dir = (
        Path(portrait_dir)
        if portrait_dir
        else results_dir / "portraits" / f"{region_key}_{portrait_type}"
    )

    map_outdir.mkdir(parents=True, exist_ok=True)
    flag_cache_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    trace: dict[str, Any] = {
        "region_key": region_key,
        "map_region": map_region or region_key,
        "marker_mode": marker_mode,
    }

    geo_kwargs: dict[str, Any] = {}
    if marker_mode == "people" and min_population is not None:
        geo_kwargs["min_pop"] = min_population

    countries = reg.geo.run(region_key, **geo_kwargs)
    trace["countries_loaded"] = len(countries)

    picks: dict[str, dict[str, Any]] = {}
    selection_trace: list[dict[str, Any]] = []
    countries_for_map = countries

    if marker_mode == "people":
        countries_for_map = _sort_countries_for_people_map(countries, n_countries)
        portrait_dir.mkdir(parents=True, exist_ok=True)

        for country in countries_for_map:
            people = reg.geo.run(
                "famous_by_country",
                country_qid=country.qid,
                category=portrait_type,
                limit_candidates=limit_candidates,
                days=pageview_days,
                score=score,
            )

            best = people[0] if people else None

            if best:
                picks[country.qid] = {
                    "qid": best.qid,
                    "label": best.name,
                    "image_url": best.image_url,
                }
                selection_trace.append(
                    {
                        "country_qid": country.qid,
                        "country_name": getattr(country, "name", None),
                        "selected_qid": best.qid,
                        "selected_label": best.name,
                        "has_image_url": bool(best.image_url),
                    }
                )
            else:
                warnings.append(
                    f"No {portrait_type} pick found for "
                    f"{getattr(country, 'name', country.qid)}"
                )
                selection_trace.append(
                    {
                        "country_qid": country.qid,
                        "country_name": getattr(country, "name", None),
                        "selected_qid": None,
                        "selected_label": None,
                        "has_image_url": False,
                    }
                )

        portrait_paths = reg.adapters.render_portraits_for_picks(
            picks,
            subject_type=_subject_type_for_portrait_type(portrait_type),
            outdir=str(portrait_dir),
        )

        def image_from_pick_path(country, pick):
            path = portrait_paths.get(country.qid)
            return {"path": path} if path else None

        spec = reg.adapters.countries_to_mapspec(
            countries_for_map,
            title=title,
            region=map_region or region_key,
            picks=picks,
            image_fn=image_from_pick_path,
            label_fn=reg.adapters.label_country_plus_pick,
        )

        show_pick_images = True if show_pick_images is None else show_pick_images
        show_flag_markers = False if show_flag_markers is None else show_flag_markers

        trace["portrait_type"] = portrait_type
        trace["n_countries_requested"] = n_countries
        trace["countries_selected"] = len(countries_for_map)
        trace["picks_selected"] = len(picks)
        trace["selection_trace"] = selection_trace
        trace["portrait_dir"] = str(portrait_dir)

    else:
        spec = reg.adapters.countries_to_mapspec(
            countries_for_map,
            title=title,
            region=map_region or region_key,
            label_fn=reg.adapters.label_country,
        )

        flag_paths = (
            cache_flags_for_markers(
                spec.markers,
                cache_dir=str(flag_cache_dir),
                width=flag_width,
                timeout=flag_timeout,
                retries=flag_retries,
            )
            if allow_live_flag_fetch
            else {}
        )

        spec = attach_flag_paths_to_mapspec(spec, flag_paths)

        trace["flag_cache_dir"] = str(flag_cache_dir)
        trace["allow_live_flag_fetch"] = allow_live_flag_fetch

    skipped_no_coords = len(countries_for_map) - len(spec.markers)
    if skipped_no_coords:
        warnings.append(f"Skipped {skipped_no_coords} records with no renderable coordinates.")

    render_kwargs = {
        "size": size,
        "marker_px": marker_px,
        "show_labels": show_labels,
        "show_country_names": show_country_names,
        "show_capital_names": show_capital_names,
        "show_pick_images": show_pick_images,
        "show_flag_markers": show_flag_markers,
        "show_fallback_dots": show_fallback_dots,
        "allow_live_image_fetch": allow_live_image_fetch,
        "flag_marker_size_px": flag_marker_size_px,
        "pick_image_size_px": pick_image_size_px,
        "min_flag_separation_px": min_flag_separation_px,
    }

    if extra_render_kwargs:
        render_kwargs.update(extra_render_kwargs)

    rendered_path = Path(
        reg.render.map(
            spec,
            outdir=str(map_outdir),
            **render_kwargs,
        )
    )

    flags_resolved = sum(
        1 for marker in spec.markers if marker.meta.get("flag_image_path")
    )
    picks_with_images = sum(
        1 for marker in spec.markers if marker.meta.get("pick_image_path")
    )

    return ArtifactResult(
        path=rendered_path,
        kind="geo_portrait_map",
        title=title,
        spec=spec,
        trace={
            **trace,
            "marker_count": len(spec.markers),
            "map_outdir": str(map_outdir),
            "render_kwargs": render_kwargs,
        },
        cache_hits={
            "flags_resolved": flags_resolved,
            "picks_with_images": picks_with_images,
        },
        cache_misses={
            "flags_missing": max(len(spec.markers) - flags_resolved, 0),
            "picks_missing_images": max(len(picks) - picks_with_images, 0),
        },
        cache_summary={
            "marker_mode": marker_mode,
            "countries_loaded": len(countries),
            "countries_rendered": len(spec.markers),
            "flags_resolved": flags_resolved,
            "picks_selected": len(picks),
            "picks_with_images": picks_with_images,
        },
        warnings=warnings,
    ).require_exists()