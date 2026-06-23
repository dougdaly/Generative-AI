# Resume Builder Notebooks

This directory contains the sequential workflow notebooks for resume building.
These notebooks implement stages 02 through 08 of the workflow.

Stage 01 is represented by raw inputs in `../sources/`.

## Stage sequence

1. `02_Canonical_Resume.ipynb` — canonical resume creation
2. `03_Job_Archetype.ipynb` — job archetype and market fit analysis
3. `04_Evidence_Review.ipynb` — evidence review and validation
4. `05_Capability_Review.ipynb` — capability review and refinement
5. `06_Resume_Positioning.ipynb` — positioning and narrative alignment
6. `07_Target_Resume_Assembly.ipynb` — target resume assembly
7. `08_Render_Target_Resume.ipynb` — final resume rendering

## Guidelines

* Keep notebooks focused on a single workflow stage.
* Use `../src/` for reusable Python logic and avoid duplicating code inside notebooks.
* Do not store generated output files in this folder.
* Add new notebooks using the `NN_Description.ipynb` naming pattern to preserve stage order.
