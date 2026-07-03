from __future__ import annotations

from pathlib import Path
from typing import Any

from numpy import trace

from agentic_multimodal.apps.result import ArtifactResult
from agentic_multimodal.skills.data.wikimedia_cache import (
    attach_flag_paths_to_mapspec,
   resolve_flag_paths_for_markers,
)
from agentic_multimodal.skills.assets.cache_policy import (
    describe_cache_policy,
    normalize_cache_policy,
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


def _flag_lookup_keys(marker) -> list[str]:
    """Possible keys for resolving a flag path for a marker."""
    raw_keys = [
        marker.meta.get("country_qid"),
        marker.meta.get("state_qid"),
        marker.meta.get("region_qid"),
        marker.meta.get("country_display_name"),
        marker.meta.get("country_name"),
        marker.label,
    ]

    return [str(key) for key in raw_keys if key]


def _attach_flag_paths_with_fallback(spec, flag_paths: dict[str, str]):
    """Attach flag paths even if resolver and adapter use slightly different keys."""
    spec = attach_flag_paths_to_mapspec(spec, flag_paths)

    for marker in spec.markers:
        if marker.meta.get("flag_image_path"):
            continue

        for key in _flag_lookup_keys(marker):
            path = flag_paths.get(key)
            if path:
                marker.meta["flag_image_path"] = str(path)
                break

    return spec

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
    cache_policy: str = "reuse",
    allow_external_calls: bool = False,
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
    show_pick_images: bool | None = None,
    show_flag_markers: bool | None = None,
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
    cache_policy = normalize_cache_policy(cache_policy)

    if marker_mode == "flags" and cache_policy in {"refresh_missing", "force_rebuild"} and not allow_external_calls:
        raise RuntimeError(
            f"cache_policy={cache_policy!r} requires allow_external_calls=True."
        )
    if marker_mode not in {"flags", "people"}:
        raise ValueError(f"marker_mode must be 'flags' or 'people', got {marker_mode!r}")
    if marker_mode == "people" and not allow_external_calls:
        raise RuntimeError(
            "marker_mode='people' currently requires allow_external_calls=True "
            "because per-country person selection is not yet manifest-backed. "
            "Use marker_mode='flags' for fully cached/default map demos."
        )

    if show_pick_images is None:
        show_pick_images = marker_mode == "people"

    if show_flag_markers is None:
        show_flag_markers = marker_mode == "flags"

    results_dir = Path(results_dir)
    map_outdir = Path(map_outdir) if map_outdir else results_dir / "maps"
    flag_cache_dir = Path(flag_cache_dir) if flag_cache_dir else results_dir / "cache" / "wikimedia" / "flags"

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

    flag_resolution = None

    flag_cache_hits: dict[str, int] = {"flags_reused": 0}
    flag_cache_misses: dict[str, int] = {
        "flags_fetched": 0,
        "flags_missing": 0,
    }

    people_cache_hits: dict[str, int] = {"picks_with_images": 0}
    people_cache_misses: dict[str, int] = {"picks_missing_images": 0}

    flags_available = 0
    flags_attached = 0
    picks_with_images = 0

    if marker_mode == "people":
        portrait_dir = (
            Path(portrait_dir)
            if portrait_dir
            else results_dir / "portraits" / f"{region_key}_{portrait_type}"
        )
        portrait_dir.mkdir(parents=True, exist_ok=True)

        countries_for_map = _sort_countries_for_people_map(countries, n_countries)
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
        people_cache_hits = {
            "picks_with_images": sum(1 for path in portrait_paths.values() if path),
        }

        people_cache_misses = {
            "picks_missing_images": max(len(picks) - people_cache_hits["picks_with_images"], 0),
        }

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

        trace["portrait_type"] = portrait_type
        trace["n_countries_requested"] = n_countries
        trace["countries_selected"] = len(countries_for_map)
        trace["picks_selected"] = len(picks)
        trace["selection_trace"] = selection_trace
        trace["portrait_dir"] = str(portrait_dir)
        trace["portrait_cache_dir"] = str(portrait_dir)
        trace["portrait_paths_resolved"] = people_cache_hits["picks_with_images"]

    else: # marker mode = flags
        spec = reg.adapters.countries_to_mapspec(
            countries_for_map,
            title=title,
            region=map_region or region_key,
            label_fn=reg.adapters.label_country,
        )

        flag_resolution = resolve_flag_paths_for_markers(
            spec.markers,
            cache_dir=str(flag_cache_dir),
            cache_policy=cache_policy,
            allow_external_calls=allow_external_calls,
            width=flag_width,
            timeout=flag_timeout,
            retries=flag_retries,
        )

        spec = _attach_flag_paths_with_fallback(spec, flag_resolution.flag_paths)
        flag_cache_hits = {
            "flags_reused": len(flag_resolution.reused),
        }

        flag_cache_misses = {
            "flags_fetched": len(flag_resolution.fetched),
            "flags_missing": len(flag_resolution.missing),
        }
        trace["flag_cache_dir"] = str(flag_cache_dir)
        trace["allow_external_calls"] = allow_external_calls
        trace["flag_manifest_path"] = str(flag_resolution.manifest_path)

    trace["cache_policy"] = cache_policy
    trace["cache_policy_description"] = describe_cache_policy(
        cache_policy,
        allow_external_calls=allow_external_calls,
    )

    picks_with_images = sum(
        1 for marker in spec.markers if marker.meta.get("pick_image_path")
    )
    
    skipped_no_coords = len(countries_for_map) - len(spec.markers)
    if skipped_no_coords:
        warnings.append(f"Skipped {skipped_no_coords} records with no renderable coordinates.")

    flags_attached = sum(
        1 for marker in spec.markers if marker.meta.get("flag_image_path")
    )
    flags_available = len(flag_resolution.flag_paths) if flag_resolution else 0

    if marker_mode == "flags" and show_flag_markers and flags_attached == 0:
        raise RuntimeError(
            "Flag cache resolution returned paths, but no flag paths were attached "
            "to map markers. Check flag path keys and attach_flag_paths_to_mapspec(...)."
        )

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

    picks_with_images = sum(
        1 for marker in spec.markers if marker.meta.get("pick_image_path")
    )

    if marker_mode == "people":
        people_cache_hits = {
            "picks_with_images": picks_with_images,
        }
        people_cache_misses = {
            "picks_missing_images": max(len(picks) - picks_with_images, 0),
        }

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
            **flag_cache_hits,
            **people_cache_hits,
        },
        cache_misses={
            **flag_cache_misses,
            **people_cache_misses,
        },
        cache_summary={
            "marker_mode": marker_mode,
            "cache_policy": cache_policy,
            "allow_external_calls": allow_external_calls,
            "description": describe_cache_policy(
                cache_policy,
                allow_external_calls=allow_external_calls,
            ),
            "countries_loaded": len(countries),
            "countries_rendered": len(spec.markers),

            "flags_available": flags_available,
            "flags_attached": flags_attached,
            "flags_resolved": flags_attached,
            "flags_reused": len(flag_resolution.reused) if flag_resolution else 0,
            "flags_fetched": len(flag_resolution.fetched) if flag_resolution else 0,
            "flags_missing": len(flag_resolution.missing) if flag_resolution else 0,

            "picks_selected": len(picks),
            "picks_with_images": picks_with_images,
            "picks_missing_images": max(len(picks) - picks_with_images, 0),
        },
        warnings=warnings,
        ).require_exists()