from __future__ import annotations

from typing import Literal


CachePolicy = Literal[
    "reuse",
    "refresh_missing",
    "force_rebuild",
    "cache_only",
]


VALID_CACHE_POLICIES: set[str] = {
    "reuse",
    "refresh_missing",
    "force_rebuild",
    "cache_only",
}


def normalize_cache_policy(policy: str) -> CachePolicy:
    """Validate and normalize cache policy names."""
    normalized = policy.strip().lower()

    if normalized not in VALID_CACHE_POLICIES:
        raise ValueError(
            f"Unknown cache_policy={policy!r}. "
            f"Expected one of: {sorted(VALID_CACHE_POLICIES)}"
        )

    return normalized  # type: ignore[return-value]


def should_read_cache(policy: CachePolicy) -> bool:
    """Whether existing cache files should be considered."""
    return policy in {"reuse", "refresh_missing", "cache_only"}


def should_write_cache(policy: CachePolicy) -> bool:
    """Whether newly fetched/generated assets should be written to cache."""
    return policy in {"reuse", "refresh_missing", "force_rebuild"}


def should_attempt_external(
    policy: CachePolicy,
    *,
    cache_hit: bool,
    allow_external_calls: bool,
) -> bool:
    """Whether the workflow may call an external API/model/source.

    External calls are controlled by both policy and an explicit user flag.
    This makes network/model usage visible in notebooks.
    """
    if not allow_external_calls:
        return False

    if policy == "cache_only":
        return False

    if policy == "force_rebuild":
        return True

    if policy == "refresh_missing":
        return not cache_hit

    if policy == "reuse":
        return not cache_hit

    raise ValueError(f"Unhandled cache policy: {policy!r}")


def describe_cache_policy(policy: str, *, allow_external_calls: bool) -> str:
    """Human-readable cache behavior for notebook output."""
    normalized = normalize_cache_policy(policy)

    if normalized == "cache_only":
        return "Use existing cache only. Do not make external calls."

    if normalized == "reuse":
        if allow_external_calls:
            return "Reuse cached assets first. Fetch/generate missing assets."
        return "Reuse cached assets only. Missing assets are reported."

    if normalized == "refresh_missing":
        if allow_external_calls:
            return "Reuse cached assets and refresh only missing assets."
        return "Refresh missing requested, but external calls are disabled."

    if normalized == "force_rebuild":
        if allow_external_calls:
            return "Ignore existing assets and rebuild from external sources."
        return "Force rebuild requested, but external calls are disabled."

    raise ValueError(f"Unhandled cache policy: {policy!r}")
