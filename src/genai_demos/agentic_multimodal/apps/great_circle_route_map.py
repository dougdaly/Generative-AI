from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_multimodal.apps.result import ArtifactResult


def run_great_circle_route_map(
    *,
    reg: Any,
    question: str,
    fail_on_missing_artifact: bool = True,
) -> ArtifactResult:
    """Build and render a great-circle route map from a natural-language request.

    This wraps the existing geo graph and converts its raw dictionary output into
    the standard Phase 2 ArtifactResult contract.
    """

    artifact = reg.graphs.geo.invoke({"question": question})

    artifact_path = artifact.get("artifact_path")
    warnings: list[str] = []

    if not artifact_path:
        message = "Geo graph did not return an artifact_path."
        if fail_on_missing_artifact:
            raise RuntimeError(message)
        warnings.append(message)
        artifact_path = ""

    answer = artifact.get("answer")
    path = Path(artifact_path) if artifact_path else Path("")

    result = ArtifactResult(
        path=path,
        kind="great_circle_route_map",
        title=question,
        spec=artifact,
        trace={
            "question": question,
            "answer": answer,
            "artifact_path": artifact.get("artifact_path"),
            "raw_keys": sorted(artifact.keys()),
            "raw_artifact": artifact,
        },
        cache_hits={},
        cache_misses={},
        cache_summary={},
        warnings=warnings,
    )

    if fail_on_missing_artifact:
        result.require_exists()

    return result