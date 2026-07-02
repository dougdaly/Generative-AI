"""Configuration helpers for Agentic Multimodal demos.

The preferred pattern is to derive paths from the repository root at runtime.
The module-level SRC/CACHE/RESULTS constants remain for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables.

    AMM_OPENAI_API_KEY is the project-scoped name. OPENAI_API_KEY is also accepted
    because many notebooks and local dev environments already use it.
    """

    model_config = SettingsConfigDict(env_prefix="AMM_", extra="ignore")

    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AMM_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.0


@dataclass(frozen=True)
class ProjectPaths:
    repo_root: Path
    src_root: Path
    package_src: Path
    cache: Path
    results: Path


def find_repo_root(start: Path | str | None = None) -> Path:
    """Find the nearest parent containing .git.

    Checks the current working directory first, then this module's location. This
    makes imports more stable from notebooks, scripts, and tests.
    """
    candidates = [Path(start).resolve()] if start is not None else [Path.cwd().resolve()]
    candidates.append(Path(__file__).resolve())

    for candidate in candidates:
        current = candidate if candidate.is_dir() else candidate.parent
        for path in [current, *current.parents]:
            if (path / ".git").exists():
                return path

    # Fallback for copied demo folders without .git. Assumes the repo layout:
    # <repo>/src/genai_demos/agentic_multimodal/core/config.py
    return Path(__file__).resolve().parents[4]


def get_project_paths(repo_root: Path | str | None = None) -> ProjectPaths:
    root = find_repo_root(repo_root)
    src_root = root / "src"
    package_src = src_root / "genai_demos" / "agentic_multimodal"
    return ProjectPaths(
        repo_root=root,
        src_root=src_root,
        package_src=package_src,
        cache=package_src / "cache",
        results=root / "results" / "agentic_multimodal",
    )


_DEFAULT_PATHS = get_project_paths()
SRC = _DEFAULT_PATHS.package_src
CACHE = _DEFAULT_PATHS.cache
RESULTS = _DEFAULT_PATHS.results
