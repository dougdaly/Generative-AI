from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent

# Locate the repository root by checking ancestors for the expected resume
# builder package and notebooks layout. This is more reliable than a hard-coded
# parent index, especially when notebook paths or package layouts change.
REPO_ROOT = None
for candidate in (SRC_DIR,) + tuple(SRC_DIR.parents):
    if (candidate / "src" / "genai_demos" / "resume_builder").is_dir() and (
        candidate / "notebooks" / "resume-builder"
    ).is_dir():
        REPO_ROOT = candidate
        break

if REPO_ROOT is None:
    raise RuntimeError(
        "Could not locate repository root containing src/genai_demos/resume_builder "
        "and notebooks/resume-builder"
    )

RESUME_BUILDER_ROOT = REPO_ROOT / "notebooks" / "resume-builder"
ARTIFACT_DIR = RESUME_BUILDER_ROOT / "artifacts"
CONTRACT_DIR = RESUME_BUILDER_ROOT / "contracts"
LAYOUT_DIR = RESUME_BUILDER_ROOT / "layouts"
SOURCE_DIR = RESUME_BUILDER_ROOT / "sources"

# Keep Path objects for downstream usage
ARTIFACT_DIR = Path(ARTIFACT_DIR)
CONTRACT_DIR = Path(CONTRACT_DIR)
LAYOUT_DIR = Path(LAYOUT_DIR)
SOURCE_DIR = Path(SOURCE_DIR)
