# Agentic Multimodal Refactor Notes

## Current status

All four notebooks run through the Phase 2 app-layer pattern:

- `01_animal_poster.ipynb`
- `02_people_series_poster.ipynb`
- `03_geo_portrait_map.ipynb`
- `04_great_circle_route_map.ipynb`

Each notebook now acts as a thin demo driver: setup, parameters, app call, display, trace inspection, and smoke check.

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
- Added country-map dedupe for duplicate country-like Wikidata entities, such as official wrapper entities and common country entities.
- Preserved the shared poster renderer for both animal and people posters.

## Phase 2 app layer

Phase 2 added reusable app workflows and a common result contract.

New common result type:

```text
src/genai_demos/agentic_multimodal/apps/result.py
```

`ArtifactResult` standardizes what each app returns:

- `path`
- `kind`
- `title`
- `spec`
- `trace`
- `cache_summary`
- `warnings`

Current app wrappers:

```text
src/genai_demos/agentic_multimodal/apps/animal_poster.py
src/genai_demos/agentic_multimodal/apps/people_series_poster.py
src/genai_demos/agentic_multimodal/apps/geo_portrait_map.py
src/genai_demos/agentic_multimodal/apps/great_circle_route_map.py
```

The notebooks now import the specific app wrapper they demonstrate, for example:

```python
from agentic_multimodal.apps.people_series_poster import run_people_series_poster
```

This keeps each notebook explicit while still allowing `apps/__init__.py` to expose convenience imports.

## App workflow contracts

### Animal poster

Workflow:

```text
grouped animal selector
    ->
prompt/image-pick records
    ->
optional image generation or cache reuse
    ->
PosterSpec
    ->
shared poster renderer
    ->
ArtifactResult
```

Current note: animal image resolution still supports a positional cache fallback for migration, but this should not be the long-term cache contract.

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

This is the strongest current app contract because it handles repeated people, sourced portraits, stable keys, manifests, strict label validation, and cache summaries.

### Geo portrait / flag map

Workflow:

```text
geographic provider
    ->
country/subdivision records
    ->
optional per-country person selection
    ->
MapSpec
    ->
flag or portrait asset resolution
    ->
map renderer
    ->
ArtifactResult
```

This app supports flag maps now and leaves room for U.S. state flags or famous-athlete-per-country maps as configuration modes rather than separate notebooks.

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

This wrapper is intentionally thin because the graph already owns route parsing and rendering.

## Notable issues fixed

### Raw QID labels

People-series posters previously risked rendering labels such as `Q23` or `Q76`. The app now repairs labels/images by QID and fails loudly if unresolved labels remain.

### Positional image joins

The people-series poster no longer assumes sorted image files align with sorted people records. Images are resolved by stable keys.

### Wikimedia rate limits

Wikimedia 429 responses are treated as temporary source failures. They should pause or stop cache population instead of silently creating placeholders.

### Duplicate country entities

Some map sources can return both a common country entity and an official wrapper entity. The map adapter now normalizes display names and dedupes renderable country markers.

### Notebook-specific registry mutation

Geo adapters now belong to the registry. The old `wire_geo_adapters(...)` path was deprecated.

## Current validation status

Manual fresh-kernel notebook runs have passed for all four demos.

Each Phase 2 notebook includes a lightweight smoke check, such as:

- artifact exists,
- expected result kind,
- nonzero record/marker count,
- expected cache behavior,
- expected file suffix.

## Remaining work

High-value next steps:

- Add automated smoke tests for the four app functions.
- Normalize cache policy names across apps.
- Improve map label collision handling.
- Add manifest-backed animal image resolution.
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
