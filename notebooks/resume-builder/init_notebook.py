from __future__ import annotations

import sys
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """
    Locate the repository root by looking for both:
    - src/genai_demos/resume_builder
    - notebooks/resume-builder
    """
    current = (start or Path.cwd()).resolve()

    for directory in (current, *current.parents):
        has_package = (directory / "src" / "genai_demos" / "resume_builder").is_dir()
        has_notebooks = (directory / "notebooks" / "resume-builder").is_dir()

        if has_package and has_notebooks:
            return directory

    raise RuntimeError(
        "Could not find repository root containing "
        "src/genai_demos/resume_builder and notebooks/resume-builder"
    )


REPO_ROOT = find_repo_root()
SRC_DIR = REPO_ROOT / "src"
NOTEBOOK_DIR = REPO_ROOT / "notebooks" / "resume-builder"
ARTIFACT_DIR = NOTEBOOK_DIR / "artifacts"
CONTRACTS_DIR = NOTEBOOK_DIR / "contracts"
LAYOUT_DIR = NOTEBOOK_DIR / "layouts"

src_str = str(SRC_DIR)
if src_str not in sys.path:
    sys.path.insert(0, src_str)

print("Repo root:", REPO_ROOT)
print("Added src to sys.path:", SRC_DIR)
print("Resume builder notebooks:", NOTEBOOK_DIR)
print("Artifacts:", ARTIFACT_DIR)

from genai_demos.resume_builder.helpers import (  # noqa: E402,F401
    extract_docx_text,
    load_json,
    load_text,
    load_yaml,
    parse_json_response,
    save_json,
    save_text,
)
