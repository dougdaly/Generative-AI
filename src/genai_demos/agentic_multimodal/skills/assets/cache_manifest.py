from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CacheManifestEntry:
    key: str
    path: str | None
    status: str  # hit | fetched | generated | missing | skipped | placeholder
    source: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class CacheManifest:
    cache_name: str
    cache_dir: str
    entries: list[CacheManifestEntry]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def manifest_path(cache_dir: str | Path, cache_name: str) -> Path:
    return Path(cache_dir) / f"{cache_name}_manifest.json"


def write_manifest(
    *,
    cache_dir: str | Path,
    cache_name: str,
    entries: list[CacheManifestEntry],
    metadata: dict[str, Any] | None = None,
) -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    manifest = CacheManifest(
        cache_name=cache_name,
        cache_dir=str(cache_dir),
        entries=entries,
        metadata=metadata or {},
    )

    path = manifest_path(cache_dir, cache_name)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def read_manifest(path: str | Path) -> dict[str, Any] | None:
    path = Path(path)

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))
