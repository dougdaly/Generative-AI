from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactResult:
    """Standard return object for agentic-multimodal app workflows."""

    path: Path
    kind: str
    title: str

    spec: Any | None = None
    trace: dict[str, Any] = field(default_factory=dict)

    cache_hits: dict[str, Any] = field(default_factory=dict)
    cache_misses: dict[str, Any] = field(default_factory=dict)

    # Backward-compatible during Phase 2 -> Phase 3 transition.
    cache_summary: dict[str, Any] = field(default_factory=dict)

    warnings: list[str] = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()

    def require_exists(self) -> "ArtifactResult":
        if not self.exists:
            raise FileNotFoundError(f"Artifact was not created: {self.path}")
        return self

    def to_dict(self, *, include_spec: bool = False) -> dict[str, Any]:
        data = {
            "path": str(self.path),
            "kind": self.kind,
            "title": self.title,
            "exists": self.exists,
            "trace": self.trace,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_summary": self.cache_summary,
            "warnings": list(self.warnings),
        }

        if include_spec:
            data["spec"] = self.spec

        return data

    def summary(self) -> str:
        status = "created" if self.exists else "missing"
        warning_text = f", warnings={len(self.warnings)}" if self.warnings else ""
        return f"{self.kind}: {self.title} ({status}) -> {self.path}{warning_text}"