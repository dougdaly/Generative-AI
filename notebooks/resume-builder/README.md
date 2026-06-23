# Resume Builder

## Overview

This folder contains the resume generation workflow built around structured source intake and a sequence of notebooks. The pipeline is designed to move from raw source materials through canonical resume creation, archetype analysis, and final target resume rendering.

Stage 01 is represented by files in `sources/`; notebooks implement stages 02 through 08.

## Workflow Stages

1. Stage 01 — Source Intake
2. Stage 02 — Canonical Resume
3. Stage 03 — Job Archetype
4. Stage 04 — Evidence Review
5. Stage 05 — Capability Review
6. Stage 06 — Resume Positioning
7. Stage 07 — Target Resume Assembly
8. Stage 08 — Render Target Resume

## Files and Notebooks

* `sources/` — raw source inputs for Stage 01
* `02_Canonical_Resume.ipynb` — Stage 02 canonical resume creation
* `03_Job_Archetype.ipynb` — Stage 03 archetype discovery
* `04_Evidence_Review.ipynb` — Stage 04 evidence review
* `05_Capability_Review.ipynb` — Stage 05 capability review
* `06_Resume_Positioning.ipynb` — Stage 06 resume positioning
* `07_Target_Resume_Assembly.ipynb` — Stage 07 target resume assembly
* `08_Render_Target_Resume.ipynb` — Stage 08 final resume rendering

## Purpose

The project is intended to:

* preserve traceability between raw career evidence and final resume claims
* structure career and market material for reuse and alignment
* separate source intake from later processing stages
* keep each stage focused on a distinct step in the resume workflow

## Notes

* `sources/` contains the input documents and datasets consumed by the workflow.
* The notebooks themselves implement the step-by-step processing and analysis.
* Keep the source folder contents aligned with Stage 01 expectations, and use sanitized data when sharing or committing files.
