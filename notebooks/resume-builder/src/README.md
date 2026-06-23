# Resume Builder Python Source

This directory contains reusable Python modules used by the resume-building workflow.

## Contents

* `capabilities.py` — capability extraction and analysis utilities
* `config.py` — configuration settings for the workflow
* `contracts.py` — schema and contract definitions
* `helpers.py` — helper utilities used across notebooks and scripts
* `render_resume.py` — high-level resume render flow
* `renderer.py` — rendering engine for final document production
* `revise.py` — revision and draft update utilities

## Usage

Import the shared code from notebooks or scripts as:

```python
from src import helpers
from src.renderer import render_resume
```

## Notes

* Keep this folder focused on reusable code, not experiment-specific notebook logic.
* If a notebook needs new Python utilities, add them here and import them from the notebook.
