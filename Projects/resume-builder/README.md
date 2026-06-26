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
* `notebooks/` — Stage 02 through Stage 08 workflow notebooks
* `src/` — shared Python code and workflow utilities
* `contracts/` — schema and contract definitions for job descriptions and search inputs
* `layouts/` — resume layout configuration files
* `artifacts/` — generated output files from notebook or script execution
* `archive/` — historical snapshots and retired notebooks or artifacts

## Project layout

This project is organized to keep raw inputs, workflow notebooks, reusable code, and generated output separate.

* `sources/` contains only source intake assets; avoid committing sensitive raw data.
* `notebooks/` contains the canonical stage notebooks.
* `src/` contains reusable code imported by notebooks and scripts.
* `artifacts/` contains generated outputs; do not edit these files manually.
* `archive/` contains retired or historical files.

## What to commit

Commit the following types of files:

* `README.md`, workflow notebooks, and source schema files
* `src/` Python modules that implement reusable logic
* `contracts/` and `layouts/` configuration files
* sample or sanitized source inputs only

## What to ignore

Generated outputs and archive files should not normally be committed:

* `artifacts/`
* `archive/`
* direct run outputs such as `*.csv`, `*.pdf`, and `*.docx`

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
