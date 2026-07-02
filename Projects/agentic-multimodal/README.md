# Agentic Multimodal

A suite of multimodal artifact-generation demos that combine structured data retrieval, image sourcing or generation, cache-aware asset handling, and deterministic rendering.

The project is not just "prompt an image model." It demonstrates a repeatable pattern for turning a high-level content request into structured records, resolved visual assets, a render specification, and a final artifact with traceable metadata.

## What this demonstrates

- Thin notebooks that call reusable app-layer workflows.
- A shared `ArtifactResult` return contract for generated artifacts.
- Structured data retrieval from providers such as Wikidata/Wikimedia.
- Entity normalization before rendering.
- Stable image joins using keys such as Wikidata QIDs.
- Cache-aware image sourcing with manifests and explicit fallback behavior.
- Shared poster rendering across generated animals and sourced people.
- Deterministic map and poster rendering after data and assets are resolved.

## Demo notebooks

Recommended order:

1. `01_animal_poster.ipynb`
2. `02_people_series_poster.ipynb`
3. `03_geo_portrait_map.ipynb`
4. `04_great_circle_route_map.ipynb`

Each notebook follows the same Phase 2 shape:

```python
setup
parameters
run app function
display result
inspect trace
smoke check
```

## App-layer workflows

The notebooks call app functions under:

```text
src/genai_demos/agentic_multimodal/apps/
```

Current app wrappers:

- `run_animal_poster(...)`
- `run_people_series_poster(...)`
- `run_geo_portrait_map(...)`
- `run_great_circle_route_map(...)`

Each app returns an `ArtifactResult` with:

- `path`: final rendered artifact
- `kind`: artifact type
- `title`: display title or request
- `spec`: render spec or raw graph artifact
- `trace`: workflow metadata
- `cache_summary`: cache and asset-resolution summary
- `warnings`: non-fatal issues surfaced by the app

Example:

```python
from agentic_multimodal.apps.people_series_poster import run_people_series_poster

result = run_people_series_poster(
    reg=reg,
    results_dir=RESULTS,
    series_key="potus",
    title="U.S. Presidents - Terms",
    mode="per_term",
    cols=6,
    cache_policy="reuse_then_source",
    expect_open_current_term=True,
)

print(result.summary())
display_image(result.path)
result.to_dict()
```

## Architecture

```text
User intent / notebook parameters
        ->
App-layer workflow
        ->
Structured data retrieval
        ->
Entity normalization and validation
        ->
Image sourcing or generation
        ->
Cache and metadata manifest
        ->
PosterSpec / MapSpec / graph artifact
        ->
Deterministic renderer
        ->
ArtifactResult
```

## Key design choices

### Registry-owned adapters

The registry exposes the shared providers, adapters, renderers, and graph workflows. Notebooks do not patch the registry at runtime.

### Shared notebook bootstrap

`notebook_bootstrap.py` owns repo discovery, import paths, result/cache paths, registry creation, and notebook display helpers. The notebooks should not duplicate setup logic.

### Stable image joins

People-series posters resolve images by stable keys, usually Wikidata QIDs, rather than by sorted filenames. This avoids stale-cache and image-mismatch bugs.

### Sourced portraits for real people

For famous real people, the default path prefers sourced Wikimedia portraits over generated likenesses. Generated images remain more appropriate for synthetic examples such as animals.

### Explicit cache behavior

Cache policies are intentional. For people-series posters, `reuse_then_source` is the preferred public-demo default because missing images are surfaced instead of silently hidden with placeholders.

### Deterministic rendering

Once data records and image assets are resolved, the final posters and maps are rendered deterministically from structured specs.

## Running the notebooks

Open the notebooks from inside the repository or project folder so `notebook_bootstrap.py` can find the project paths.

Typical first cell:

```python
from notebook_bootstrap import display_image, image_files, init_notebook

ctx, reg = init_notebook()

REPO_ROOT = ctx.repo_root
PROJECT_ROOT = ctx.project_root
CACHE = ctx.cache
RESULTS = ctx.results
```

For image generation demos, configure the relevant model/API settings used by the project. For sourced Wikimedia assets, live network access may be needed the first time a cache is populated.

## Cache behavior

The project writes artifacts and cache files under the project results/cache layout. It can also reuse legacy artifact/cache folders when present.

Important cache patterns:

- People portraits are keyed by `image_key` and tracked through a manifest.
- Wikimedia flags are cached before rendering maps.
- Animal images can be generated or reused from cache. A positional cache fallback exists only for migration from older generated image folders.
- Live Wikimedia requests can be rate limited. Rate limits should stop or pause the cache-fill pass rather than silently creating bad artifacts.

## Current limitations

- Map label collision handling is basic. Dense regions such as Europe can still overlap if many labels are enabled.
- Animal image caching is safer than the original notebook, but it is not yet as manifest-backed as the people-series cache.
- The NBA MVP / future sports-award example remains a future provider idea until a real provider emits stable person records.
- Cache policy names could be normalized across all apps.
- The current validation is mostly notebook smoke checks rather than automated tests.

## Next steps

- Add lightweight smoke tests for the four app functions.
- Normalize cache policy names and behavior across apps.
- Improve map label collision handling.
- Add manifest-backed animal image resolution.
- Add a real non-Wikidata or sports-award provider.
- Add small fixture-based tests for app-layer traces and `ArtifactResult` outputs.
