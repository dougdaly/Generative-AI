# skills/adapters/picks_to_portraits.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Mapping

from agentic_multimodal.skills.image_gen import generate_person_images

def _name_of(p) -> str | None:
    # supports dict or pydantic model
    if p is None:
        return None
    if isinstance(p, dict):
        return p.get("label") or p.get("name")
    return getattr(p, "name", None)

def _image_url_of(p) -> str | None:
    if p is None:
        return None
    if isinstance(p, dict):
        return p.get("image_url")
    return getattr(p, "image_url", None)

def render_portraits_for_picks(
    picks: Dict[str, dict],              # {country_qid: {"label":..., "image_url":..., ...}}
    outdir: str,
    *,
    steps: int = 28,
    cfg: float = 6.0,
    size=(512, 768),
    seed: int = 1337,
    skip_existing: bool = True,
):
    """
    Returns: {country_qid -> local_png_path}
    If a pick has image_url, we pass it as the reference; otherwise we do text2img.
    """
    Path(outdir).mkdir(parents=True, exist_ok=True)

    # Build (name, year, ref) triples; year=None; ref = URL or None
    pairs = []
    qids  = []   # keep order to zip paths back to country ids
    for qid, p in picks.items():
        # p is a dict: {"qid","label","image_url",...}
        display = p.get("label") or p.get("name") or p.get("qid")
        ref_url = p.get("image_url")
        pairs.append((display, None, ref_url))
        qids.append(qid)

    # Generate images (uses ref when available; falls back to text2img)
    paths = generate_person_images(
        pairs,
        outdir=outdir,
        steps=steps,
        cfg=cfg,
        size=size,
        seed=seed,
        skip_existing=skip_existing,
    )

    # Map back to {country_qid: path}
    return {qid: path for qid, path in zip(qids, paths)}
