from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_multimodal.apps.result import ArtifactResult
from agentic_multimodal.skills.assets.cache_policy import (
    describe_cache_policy,
    normalize_cache_policy,
)


def run_great_circle_route_map(
    *,
    reg: Any,
    question: str,
    cache_policy: str = "reuse",
    allow_external_calls: bool = False,
    fail_on_missing_artifact: bool = True,
) -> ArtifactResult:
    """Build and render a great-circle route map from a natural-language request.

    This wraps the existing geo graph and converts its raw dictionary output into
    the standard ArtifactResult contract.

    Note:
        Cache behavior is currently owned by the underlying geo graph. The app
        records cache_policy and allow_external_calls for consistency, but does
        not yet enforce those controls inside the graph.
    """
    cache_policy = normalize_cache_policy(cache_policy)

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
            "cache_policy": cache_policy,
            "allow_external_calls": allow_external_calls,
            "cache_policy_description": describe_cache_policy(
                cache_policy,
                allow_external_calls=allow_external_calls,
            ),
            "cache_behavior": "graph_owned",
            "cache_policy_enforced": False,
        },
        cache_hits={},
        cache_misses={},
        cache_summary={
            "cache_policy": cache_policy,
            "allow_external_calls": allow_external_calls,
            "description": describe_cache_policy(
                cache_policy,
                allow_external_calls=allow_external_calls,
            ),
            "cache_behavior": "graph_owned",
            "cache_policy_enforced": False,
        },
        warnings=warnings,
    )

    if fail_on_missing_artifact:
        result.require_exists()

    return result