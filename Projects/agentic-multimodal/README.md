# Agentic Multimodal

A suite of multimodal artifact-generation demos that combine structured data retrieval, image sourcing or generation, explicit cache behavior, and deterministic rendering.

The project is not just "prompt an image model." It demonstrates a repeatable pattern for turning a high-level content request into structured records, resolved visual assets, a render specification, and a final artifact with traceable metadata.

## What this demonstrates

- Thin notebooks that call reusable app-layer workflows.
- A shared `ArtifactResult` return contract for generated artifacts.
- Structured data retrieval from providers such as Wikidata/Wikimedia.
- Entity normalization and validation before rendering.
- Stable image joins using keys such as Wikidata QIDs.
- Explicit cache policies that make external calls visible and optional.
- Cache-aware image sourcing with manifests or cache summaries.
- Shared poster rendering across generated animals and sourced people.
- Deterministic map and poster rendering after data and assets are resolved.

## Demo notebooks

Recommended order:

1. `01_animal_poster.ipynb`
2. `02_people_series_poster.ipynb`
3. `03_geo_portrait_map.ipynb`
4. `04_great_circle_route_map.ipynb`

Each notebook follows the same shape:

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
- `cache_hits`: cache reuse counters
- `cache_misses`: fetched/generated/missing counters
- `cache_summary`: compact cache and asset-resolution summary
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
    cache_policy="reuse",
    allow_external_calls=False,
    allow_placeholders=False,
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

## Cache policy contract

Most notebooks default to cache reuse with external calls disabled:

```python
CACHE_POLICY = "reuse"
ALLOW_EXTERNAL_CALLS = False
```

The shared cache policy names are:

| Policy | Meaning |
|---|---|
| `reuse` | Use existing cache first. Missing assets are fetched or generated only when `allow_external_calls=True`. |
| `refresh_missing` | Reuse valid cached assets and fetch/generate only missing assets. Requires `allow_external_calls=True`. |
| `force_rebuild` | Ignore existing cached assets and rebuild. Requires `allow_external_calls=True`. |
| `cache_only` | Read cache only. Never make external calls. |

People-series posters also expose:

```python
ALLOW_PLACEHOLDERS = False
```

Placeholders are intentionally separate from cache policy so missing source images do not get hidden accidentally.

## Key design choices

### Registry-owned adapters

The registry exposes the shared providers, adapters, renderers, and graph workflows. Notebooks do not patch the registry at runtime.

### Shared notebook bootstrap

`notebook_bootstrap.py` owns repo discovery, import paths, result/cache paths, registry creation, and notebook display helpers. The notebooks should not duplicate setup logic.

### Stable image joins

People-series posters resolve images by stable keys, usually Wikidata QIDs, rather than by sorted filenames. This avoids stale-cache and image-mismatch bugs.

### Sourced portraits for real people

For famous real people, the default path prefers sourced Wikimedia portraits over generated likenesses. Generated images remain more appropriate for synthetic examples such as animals.

### Explicit external calls

External calls are opt-in at the notebook level. A normal demo run should be able to reuse cached assets without calling Wikimedia or an image-generation model.

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

For normal cached demos, use:

```python
CACHE_POLICY = "reuse"
ALLOW_EXTERNAL_CALLS = False
```

To populate missing assets intentionally, use:

```python
CACHE_POLICY = "refresh_missing"
ALLOW_EXTERNAL_CALLS = True
```

To rebuild generated or sourced assets intentionally, use:

```python
CACHE_POLICY = "force_rebuild"
ALLOW_EXTERNAL_CALLS = True
```

## Current cache behavior

- People portraits are keyed by `image_key`, usually Wikidata QID, and are resolved by a manifest-backed image resolver.
- Animal posters now use the same public cache policy contract. Cached runs do not generate images unless external calls are enabled.
- Geo flag maps use the shared cache policy contract. Cached flag runs do not call Wikimedia by default.
- Geo people mode is supported as an explicit external-call mode, but per-country person selection is not yet manifest-backed.
- Great-circle route maps record cache policy settings, but cache enforcement is currently owned by the underlying geo graph.
- Live Wikimedia requests can be rate limited. Rate limits should stop or pause the cache-fill pass rather than silently creating bad artifacts.

## Current limitations

- Map label collision handling is basic. Dense regions such as Europe can still overlap if many labels are enabled.
- Animal image caching works with explicit policies, but it is not yet as manifest-backed as the people-series cache.
- Geo people mode requires `allow_external_calls=True` until per-country selection has a manifest-backed cache.
- The great-circle route app records cache settings but does not yet enforce them inside the graph.
- The NBA MVP / future sports-award example remains a future provider idea until a real provider emits stable person records.
- The current validation is mostly notebook smoke checks rather than automated tests.

## Next steps

- Add lightweight smoke tests for the four app functions.
- Standardize manifest files across people portraits, animal images, geo flags, and geo portraits.
- Improve map label collision handling.
- Add manifest-backed animal image resolution.
- Add manifest-backed per-country people selection for geo people maps.
- Add a real non-Wikidata or sports-award provider.
- Add small fixture-based tests for app-layer traces and `ArtifactResult` outputs.
