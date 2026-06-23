# Generative AI Notebooks Workspace

This workspace is a collection of generative AI experiments, demos, and project notebooks organized by theme and capability.

## Purpose

The repo contains standalone notebooks, demo folders, and one structured subproject (`resume-builder`). It is intended for exploration, proof-of-concept work, and reusable components rather than a single packaged application.

## Main areas

- `agentic_multimodal/` — an agentic multimodal demo workflow with notebooks and artifacts.
- `archival_restore/` — archival restoration notebooks and debug materials.
- `fast_api/` — FastAPI demo scripts and notebook examples.
- `lora_coverage_adapter/` — tokenizer / adapter packaging assets and README.
- `pt_supportrouter/` — support router/tokenizer package assets and README.
- `resume-builder/` — a multi-stage resume generation workflow with source intake, canonical resume processing, archetype analysis, and output rendering.
- `sotu-speech-analytics/` — speech analytics notebook(s).
- `wgan_gp_afhq/` — WGAN-GP notebook for AFHQ.

## Notebook organization

The workspace notebooks are now grouped into category folders for easier navigation:

- `vision/` — image, diffusion, GAN, and visual modeling notebooks
- `agents/` — agentic AI, RAG, and multi-agent workflow notebooks
- `recommendation/` — recommender system and ranking notebooks
- `nlp/` — NLP and prompt tuning notebooks
- `misc/` — miscellaneous notebooks and other experiments

Each category folder contains its own `README.md` with a summary of the notebooks and workflow focus.

### Category folder READMEs

- `vision/README.md`
- `agents/README.md`
- `recommendation/README.md`
- `nlp/README.md`
- `misc/README.md`

## Resume Builder

The `resume-builder/` subfolder is a project with its own notebooks and source structure. Its workflow stages include:

1. Stage 01 — Source Intake
2. Stage 02 — Canonical Resume
3. Stage 03 — Job Archetype
4. Stage 04 — Evidence Review
5. Stage 05 — Capability Review
6. Stage 06 — Resume Positioning
7. Stage 07 — Target Resume Assembly
8. Stage 08 — Render Target Resume

The source intake stage is represented by `resume-builder/sources/`.

## Notes

- There is no root package or single deployable app in this workspace.
- Generated outputs and large tokenizer files may exist in subfolders; prefer `.gitignore` rules for generated artifacts and private source materials.
- For project-specific details, refer to the README files inside each folder.
