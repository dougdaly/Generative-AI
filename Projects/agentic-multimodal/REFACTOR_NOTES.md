# Agentic Multimodal Refactor Notes

## Current status

All four notebooks run through the app-layer pattern:

- `01_animal_poster.ipynb`
- `02_people_series_poster.ipynb`
- `03_geo_portrait_map.ipynb`
- `04_great_circle_route_map.ipynb`

Each notebook now acts as a thin demo driver: setup, parameters, app call, display, trace inspection, and smoke check.

Phase 3 cache behavior is now explicit for the main asset-heavy demos:

- people-series portraits
- animal poster images
- geo flag maps

The great-circle route app records cache settings, but cache enforcement remains graph-owned.

## Phase 1 closeout

Phase 1 converted the original single notebook into four focused notebooks and stabilized the underlying data/rendering contracts.

Completed Phase 1 design changes:

- Split the original notebook into four demo notebooks.
- Added shared `notebook_bootstrap.py` for repo discovery, import paths, cache/results paths, registry creation, and display helpers.
- Moved geo adapter ownership into the registry, removing notebook-specific adapter wiring.
- Introduced a generic `SeriesRecord` contract for people-series rendering.
- Resolved people images by stable `image_key` values, usually Wikidata QIDs, instead of sorted file order.
- Added manifest-backed people image resolution.
- Preferred sourced Wikimedia portraits for real people.
- Added generic Wikidata label/image repair for raw-QID failure cases.
- Added fail-loud validation before rendering public people-series posters.
- Added Wikimedia rate-limit handling for image downloads.
- Added country display-name normalization for map labels.
- Added country-map dedupe for duplicate country-like Wikidata entities.
- Preserved the shared poster renderer for both animal and people posters.

## Phase 2 app layer

Phase 2 added reusable app workflows and a common result contract.

Current app wrappers:

```text
src/genai_demos/agentic_multimodal/apps/animal_poster.py
src/genai_demos/agentic_multimodal/apps/people_series_poster.py
src/genai_demos/agentic_multimodal/apps/geo_portrait_map.py
src/genai_demos/agentic_multimodal/apps/great_circle_route_map.py
```

`ArtifactResult` standardizes what each app returns:

- `path`
- `kind`
- `title`
- `spec`
- `trace`
- `cache_hits`
- `cache_misses`
- `cache_summary`
- `warnings`

The notebooks import the specific app wrapper they demonstrate, for example:

```python
from agentic_multimodal.apps.people_series_poster import run_people_series_poster
```

This keeps each notebook explicit while still allowing `apps/__init__.py` to expose convenience imports.

## Phase 3 cache contract

Phase 3 made cache behavior explicit and moved notebooks toward reproducible cache-first defaults.

Shared public cache settings:

```python
CACHE_POLICY = "reuse"
ALLOW_EXTERNAL_CALLS = False
```

Supported policy names:

- `reuse`
- `refresh_missing`
- `force_rebuild`
- `cache_only`

Policy behavior:

```text
reuse + False          -> use cache only; report missing assets
reuse + True           -> use cache first; fetch/generate missing assets
refresh_missing + True -> reuse cache and fill missing assets
force_rebuild + True   -> ignore cache and rebuild assets
cache_only             -> never make external calls
```

Placeholders are separate from cache policy. People-series posters use:

```python
ALLOW_PLACEHOLDERS = False
```

This avoids hiding missing portraits behind placeholder images unless explicitly requested.

## App workflow contracts

### Animal poster

Workflow:

```text
grouped animal selector
    ->
prompt/image-pick records
    ->
cache reuse or explicit image generation
    ->
PosterSpec
    ->
shared poster renderer
    ->
ArtifactResult
```

Phase 3 status:

- Supports `cache_policy`.
- Supports `allow_external_calls`.
- Cached reuse path validated.
- `force_rebuild` generation path validated.
- Positional cache fallback remains available only as a migration option.

### People-series poster

Workflow:

```text
provider records
    ->
generic QID label/image repair
    ->
SeriesRecord rows
    ->
keyed image resolution
    ->
PosterSpec
    ->
shared poster renderer
    ->
ArtifactResult
```

Phase 3 status:

- Supports `cache_policy`.
- Supports `allow_external_calls`.
- Supports explicit `allow_placeholders`.
- Cached reuse path validated.
- Refresh/rebuild path validated.
- Legacy policy names such as `reuse_then_source` were removed from the public app/notebook API.

### Geo portrait / flag map

Workflow:

```text
geographic provider
    ->
country/subdivision records
    ->
MapSpec
    ->
flag cache resolution or optional people selection
    ->
map renderer
    ->
ArtifactResult
```

Phase 3 status:

- Flag mode supports `cache_policy`.
- Flag mode supports `allow_external_calls`.
- Cached flag reuse path validated.
- Flag attachment is validated before rendering so smoke checks do not pass while the renderer shows fallback dots.
- People mode is guarded: it currently requires `allow_external_calls=True` because per-country person selection is not yet manifest-backed.

### Great-circle route map

Workflow:

```text
natural-language route question
    ->
geo graph
    ->
route artifact
    ->
ArtifactResult
```

Phase 3 status:

- App records `cache_policy` and `allow_external_calls`.
- App marks cache behavior as `graph_owned`.
- Cache policy is not yet enforced inside the geo graph.

## Notable issues fixed

### Raw QID labels

People-series posters previously risked rendering labels such as `Q23` or `Q76`. The app now repairs labels/images by QID and fails loudly if unresolved labels remain.

### Positional image joins

The people-series poster no longer assumes sorted image files align with sorted people records. Images are resolved by stable keys.

### Wikimedia rate limits

Wikimedia 429 responses are treated as temporary source failures. They should pause or stop cache population instead of silently creating placeholders.

### Duplicate country entities

Some map sources can return both a common country entity and an official wrapper entity. The map adapter now normalizes display names and dedupes renderable country markers.

### Geo flag fallback dots

Geo flag smoke checks were updated to validate attached marker paths, not just resolver-returned paths. This prevents a false pass where cached flags exist but the renderer still shows fallback dots.

### Notebook-specific registry mutation

Geo adapters now belong to the registry. The old `wire_geo_adapters(...)` path was deprecated.

## Current validation status

Manual fresh-kernel notebook runs have passed for all four demos.

Validated cache behavior:

- people-series poster: cache reuse and refresh/rebuild behavior
- animal poster: cache reuse and `force_rebuild` generation behavior
- geo flag map: cache reuse with external calls disabled
- great-circle route map: app-layer result and graph-owned cache trace

Each notebook includes a lightweight smoke check, such as:

- artifact exists,
- expected result kind,
- nonzero record/marker count,
- expected cache behavior,
- expected file suffix.

## Remaining work

High-value next steps:

- Add automated smoke tests for the four app functions.
- Standardize manifest files across all asset caches.
- Add manifest-backed animal image resolution.
- Add manifest-backed per-country people selection for geo people maps.
- Improve map label collision handling.
- Add a real NBA MVP or sports-award provider rather than keeping it as a stub idea.
- Add small fixture datasets so tests do not require live Wikidata/Wikimedia access.
- Add app-level examples to the README once the API stabilizes further.

## Public positioning

The project should be described as structured multimodal artifact generation.

Stronger framing:

```text
User intent or notebook config
        ->
Structured data retrieval
        ->
Entity selection and normalization
        ->
Image sourcing or generation
        ->
Cache and metadata manifest
        ->
PosterSpec / MapSpec / route artifact
        ->
Deterministic renderer
        ->
Final artifact and trace
```

Avoid positioning it as only image prompting. The more interesting engineering story is the orchestration around data, assets, cache, validation, rendering, and traceability.
