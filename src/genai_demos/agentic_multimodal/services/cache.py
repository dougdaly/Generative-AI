# src/agentic_multimodal/services/cache.py
from __future__ import annotations
from pathlib import Path
import hashlib, json

class Cache:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def key(self, *parts: str) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(str(p).encode())
        return h.hexdigest()

    def path_for(self, key: str, suffix: str = "") -> Path:
        d = self.base_dir / "runs" / key[:2] / key[2:4] / key
        d.mkdir(parents=True, exist_ok=True)
        return d / f"artifact{suffix}"

    def put_json(self, key: str, obj) -> Path:
        p = self.path_for(key, ".json")
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

