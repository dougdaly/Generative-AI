"""Shared setup helpers for the Agentic Multimodal notebooks.

Keep notebook cells focused on the demo. Repo discovery, sys.path setup,
cache/result paths, registry creation, and common display helpers live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable, Sequence

_IMAGE_EXTENSIONS = ("*.webp", "*.png", "*.jpg", "*.jpeg")

__all__ = [
    "NotebookContext",
    "find_repo_root",
    "find_project_root",
    "image_files",
    "setup_notebook",
    "init_notebook",
    "print_context",
    "display_image",
]

def find_repo_root(start: Path | str | None = None) -> Path:
    """Find the nearest parent containing .git."""
    current = Path(start or Path.cwd()).resolve()
    for path in [current, *current.parents]:
        if (path / ".git").exists():
            return path
    raise RuntimeError("Could not find repo root. Open this notebook from inside the repo.")


def find_project_root(repo_root: Path, start: Path | str | None = None) -> Path:
    """Find the project folder that owns src/genai_demos/agentic_multimodal.

    Supports both layouts:
    - <repo>/src/genai_demos/agentic_multimodal
    - <repo>/Projects/agentic-multimodal/src/genai_demos/agentic_multimodal
    """
    current = Path(start or Path.cwd()).resolve()
    candidates = [
        current,
        *current.parents,
        repo_root,
        repo_root / "Projects" / "agentic-multimodal",
    ]

    for candidate in _dedupe_paths(candidates):
        if (candidate / "src" / "genai_demos" / "agentic_multimodal").exists():
            return candidate

    # Fall back to the repo root so the error points at the expected src path.
    return repo_root


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def image_files(directory: Path | str) -> list[str]:
    """Return image files in a stable order."""
    directory = Path(directory)
    files: list[Path] = []
    for pattern in _IMAGE_EXTENSIONS:
        files.extend(directory.glob(pattern))
    return [str(path) for path in sorted(files)]


@dataclass(frozen=True)
class NotebookContext:
    repo_root: Path
    project_root: Path
    src_root: Path
    package_src: Path
    cache: Path
    results: Path
    artifact_roots: tuple[Path, ...]
    cache_roots: tuple[Path, ...]

    def ensure_dirs(self, *paths: Path | str) -> None:
        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)

    def resolve_dir(
        self,
        relative_path: str | Path,
        *,
        preferred_root: Path,
        legacy_roots: Sequence[Path] = (),
        create: bool = True,
        prefer_existing_images: bool = True,
    ) -> Path:
        """Resolve a data/image directory with support for legacy artifact/cache locations."""
        rel = Path(relative_path)
        candidates = _dedupe_paths([preferred_root / rel, *[root / rel for root in legacy_roots]])

        if prefer_existing_images:
            for candidate in candidates:
                if candidate.exists() and image_files(candidate):
                    return candidate

        preferred = candidates[0]
        if create:
            preferred.mkdir(parents=True, exist_ok=True)
        return preferred

    def find_existing_files(self, filename: str, roots: Sequence[Path] | None = None) -> list[Path]:
        roots = roots or (self.results, *self.artifact_roots)
        matches: list[Path] = []
        for root in roots:
            if root.exists():
                matches.extend(root.rglob(filename))
        return sorted(_dedupe_paths(matches))


def setup_notebook(start: Path | str | None = None) -> tuple[NotebookContext, object]:
    """Prepare import paths, result/cache directories, and the shared registry."""
    start_path = Path(start) if start else Path.cwd()
    repo_root = find_repo_root(start_path)
    project_root = find_project_root(repo_root, start_path)

    src_root = project_root / "src"
    genai_src = src_root / "genai_demos"

    for path in [src_root, genai_src]:
        path_str = str(path)
        if path.exists() and path_str not in sys.path:
            sys.path.insert(0, path_str)

    package_src = genai_src / "agentic_multimodal"
    cache = package_src / "cache"
    results = project_root / "results" / "agentic_multimodal"

    artifact_roots = tuple(
        path
        for path in _dedupe_paths(
            [
                project_root / "artifacts",
                repo_root / "artifacts",
                repo_root / "Projects" / "agentic-multimodal" / "artifacts",
                Path.cwd() / "artifacts",
            ]
        )
        if path.exists()
    )
    cache_roots = tuple(
        path
        for path in _dedupe_paths(
            [
                project_root / "cache",
                repo_root / "cache",
                repo_root / "Projects" / "agentic-multimodal" / "cache",
                Path.cwd() / "cache",
            ]
        )
        if path.exists()
    )

    ctx = NotebookContext(
        repo_root=repo_root,
        project_root=project_root,
        src_root=src_root,
        package_src=package_src,
        cache=cache,
        results=results,
        artifact_roots=artifact_roots,
        cache_roots=cache_roots,
    )

    ctx.ensure_dirs(cache, results, results / "posters", results / "maps")

    from agentic_multimodal.services.registry import make_registry

    reg = make_registry(project_root)
    return ctx, reg


def print_context(ctx: NotebookContext) -> None:
    print("Repo root:", ctx.repo_root)
    print("Project root:", ctx.project_root)
    print("Package src:", ctx.package_src)
    print("Cache:", ctx.cache)
    print("Results:", ctx.results)
    if ctx.artifact_roots:
        print("Legacy artifact roots:", [str(path) for path in ctx.artifact_roots])
    if ctx.cache_roots:
        print("Legacy cache roots:", [str(path) for path in ctx.cache_roots])


def display_image(path: Path | str) -> None:
    """Display an image path in a notebook, preferring the project helper."""
    try:
        from agentic_multimodal.notebook_utils import display_image as project_display_image

        project_display_image(str(path))
    except Exception:
        from IPython.display import Image, display

        display(Image(filename=str(path)))

def init_notebook(
    start: Path | str | None = None,
    *,
    show_context: bool = True,
) -> tuple[NotebookContext, object]:
    """Set up a demo notebook and optionally print the resolved paths."""
    ctx, reg = setup_notebook(start=start)

    if show_context:
        print_context(ctx)

    return ctx, reg