## Current status

All four notebooks run:
- animal poster
- people-series poster
- geo portrait / flag map
- great-circle route map

## Completed design changes

- Shared notebook bootstrap
- Registry-owned adapters, no notebook-specific geo wiring
- Generic SeriesRecord contract
- Keyed image assets by image_key / QID
- Manifest-backed people image cache
- Sourced portraits preferred for real people
- Wikimedia rate-limit handling
- Geo country display-name normalization
- Geo dedupe for duplicate country-like Wikidata entities
- Shared poster renderer for animal and people posters

## Remaining Phase 2 candidates

- Add apps/ layer
- Add ArtifactResult
- Add smoke tests
- Improve map label collision handling
- Add NBA MVP or other non-Wikidata provider as a real provider, not STUB
- Normalize cache policy names