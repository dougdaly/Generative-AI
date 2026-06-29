"""Utility helpers for Jupyter-facing demos.

Keep notebooks thin. Import from here to:
- build a registry with all skills/adapters (`make_registry`)
- route+run a user prompt through the correct flow (`run_flow`)
- display images cleanly in notebooks (`show_image`)
- write/read provenance (`save_manifest`, `tail_manifest`)
- locate repo roots and standard result folders (`resolve_root`, `results_dir_for`)

Example (in notebooks/agentic-multimodal/01_overview.ipynb):

```python
import asyncio, pathlib as p
from agentic_multimodal.notebook_utils import (
    resolve_root, results_dir_for, make_registry,
    run_flow, show_image, tail_manifest, save_manifest
)

ROOT = resolve_root()                    # finds project root by pyproject.toml or .git
RESULTS = results_dir_for("agentic_multimodal", root=ROOT)
REG, settings, MANIFEST = make_registry(ROOT, results_subdir="agentic_multimodal")

prompt = "give me a poster showing all US presidents and the years they were in office"
res = asyncio.run(run_flow(prompt, REG))
show_image(res["output_path"])          # inline PNG
save_manifest(MANIFEST, res)              # append JSON line
print(tail_manifest(MANIFEST, n=1)[0])
```

Notes:
- This module assumes your package layout from `src/agentic_multimodal/` with
  `services/{settings,cache,registry}.py`, `skills/`, `graphs/`, and `router.py` present.
- If you haven’t registered a given tool yet, `make_registry` will raise a clear error.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from pydantic import ValidationError
from IPython.display import Image, display
from agentic_multimodal.services.registry import make_registry as _make_reg
from agentic_multimodal.services.settings import Settings  # for debug helper

# Soft IPython import so this module also works in non-notebook contexts
try:
    from IPython.display import Image, display  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    def display(*_, **__):  # type: ignore
        pass




def display_image(path: str | Path) -> None:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path.resolve()}")

    display(Image(filename=str(path)))

# --- Repo & paths -----------------------------------------------------------

def resolve_root(start: Optional[Path] = None) -> Path:
    """Return project root by walking up to find pyproject.toml or .git.
    Falls back to current working directory.
    """
    p = Path.cwd() if start is None else Path(start).resolve()
    for parent in [p, *p.parents]:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    return p


def results_dir_for(subdir: str, *, root: Optional[Path] = None) -> Path:
    root = resolve_root(root)
    out = root / "results" / subdir
    out.mkdir(parents=True, exist_ok=True)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    return out

# --- Imports from package ---------------------------------------------------
# We import lazily inside functions to fail gracefully if a module isn’t present yet.

# --- Display helpers --------------------------------------------------------

def show_image(path: Path | str) -> None:
    """Display an image inline in a notebook (no custom styling).
    Safe to call outside notebooks; will no-op if IPython.display is absent.
    """
    if Image is None:
        print(f"[image] {path}")
        return
    display(Image(filename=str(path)))

# --- Manifest & provenance --------------------------------------------------

def save_manifest(manifest_path: Path | str, record: Dict[str, Any]) -> None:
    """Append a single JSON line record to a manifest file."""
    mpath = Path(manifest_path)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    with mpath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def tail_manifest(manifest_path: Path | str, n: int = 5) -> List[Dict[str, Any]]:
    """Return the last n JSON objects from a manifest.jsonl file."""
    mpath = Path(manifest_path)
    if not mpath.exists():
        return []
    lines = mpath.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines[-n:]]

# --- Registry bootstrap -----------------------------------------------------

@dataclass
class RegistryBundle:
    registry: Any
    settings: Any
    manifest_path: Path


def debug_settings(env_path: Path | None = None):
    try:
        s = Settings(_env_file=str(env_path) if env_path and env_path.exists() else None)
        print("✅ Settings OK"); return s
    except ValidationError as e:
        print("❌ Settings validation failed:")
        for err in e.errors():
            loc = ".".join(str(x) for x in err.get("loc", []))
            print(f"- {loc}: {err['msg']}  (input={err.get('input')!r})")
        raise

# --- Flow execution ---------------------------------------------------------

async def run_flow(prompt: str, reg: Any) -> Dict[str, Any]:
    """Route a natural-language `prompt`, run the appropriate flow, and
    return a record with provenance fields ready to append to a manifest.

    Returns dict with keys:
      - run_id: str
      - kind: "person" | "geo" | other
      - request: serialized request model (if available)
      - spec: serialized output spec (PosterSpec/MapSpec)
      - output_path: filesystem path to the rendered artifact
      - tool_meta (optional): any extra metadata the flows choose to return
    """
    # Lazy imports to avoid hard coupling at import time
    from agentic_multimodal.router import route  # type: ignore
    from agentic_multimodal.graphs.person_flow import run as run_person_flow  # type: ignore
    from agentic_multimodal.graphs.geo_flow import run as run_geo_flow  # type: ignore

    kind, req = route(prompt)
    run_id = f"{kind}-{uuid.uuid4().hex[:8]}"

    if kind == "person":
        spec = await run_person_flow(req, reg)
        # Expect PosterRenderer to return a path inside spec or via meta
        output_path = Path(spec.model_dump().get("path") or spec.model_dump().get("output_path", ""))
        if not output_path:
            # Allow poster renderer to stash path in items[0].image.path; then collect to a final collage path
            items = spec.model_dump().get("items", [])
            if items and isinstance(items[0], dict):
                output_path = Path(items[0].get("image", {}).get("path", ""))
        record = {
            "run_id": run_id,
            "kind": kind,
            "request": getattr(req, "model_dump", lambda: req)(),
            "spec": spec.model_dump() if hasattr(spec, "model_dump") else spec,
            "output_path": str(output_path),
        }
        return record

    if kind == "geo":
        spec = await run_geo_flow(req, reg)
        out = spec.model_dump() if hasattr(spec, "model_dump") else spec
        output_path = Path(out.get("path", ""))
        record = {
            "run_id": run_id,
            "kind": kind,
            "request": getattr(req, "model_dump", lambda: req)(),
            "spec": out,
            "output_path": str(output_path),
        }
        return record

    # Unknown kind: surface the router's decision for inspection
    return {"run_id": run_id, "kind": str(kind), "request": getattr(req, "model_dump", lambda: req)()} 

def make_people_poster(
    reg,
    *,
    series_key: str,
    title: str,
    layout: str = "per_term",     # "per_term" | "per_person_auto"
    outdir: str = None,
    outpath: str = None,
    cols: int = 6,
    gen_kwargs: dict | None = None,   # steps, guidance_scale, size, seed...
):
    people = reg.series.run(series_key)
    from agentic_multimodal.skills.adapters import name_year_pairs
    from agentic_multimodal.skills.image_gen import generate_person_images

    pairs = name_year_pairs(people, mode=layout)
    outdir = outdir or f"artifacts/{series_key}_{layout}_portraits"
    paths = generate_person_images(pairs, outdir=outdir, **(gen_kwargs or {}))

    if layout == "per_term":
        spec = reg.adapters.people_per_term(people, title=title, image_paths=paths, cols=cols)
    else:
        spec = reg.adapters.people_per_person(people, title=title, image_paths=paths, cols=cols)

    outpath = outpath or f"artifacts/poster_{series_key}_{layout}.webp"
    reg.render.poster(spec, outpath=outpath)
    return outpath
