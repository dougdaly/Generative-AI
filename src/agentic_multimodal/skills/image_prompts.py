# skills/image_prompts.py
from __future__ import annotations
import re, yaml, os
from typing import Optional, Iterable

def era_hint(year: Optional[str]) -> str:
    if not year: return ""
    try: y = int(year[:4])
    except: return ""
    if y < 1500: return "medieval attire"
    if y < 1700: return "Renaissance attire"
    if y < 1800: return "18th-century attire, powdered wig"
    if y < 1900: return "19th-century attire"
    if y < 1950: return "early 20th-century attire"
    return "modern attire"

BASE_POS = (
    "cartoon portrait, {name}, solo, single subject, bust-length, centered, "
    "clean background, flat shading, flat colors, minimal lines"
)
BASE_NEG = (
    "group, crowd, second person, extra face, extra head, duplicate, twins, "
    "reflection, mirror, collage, text, watermark, logo, hands, full body"
)

# Optional external YAML for easy editing (no code changes needed)
_OVERRIDES_PATH = os.environ.get("AM_OVERRIDES_YAML", "assets/prompts/overrides.yaml")

def _canon(s: str) -> str:
    return re.sub(r"\W+", " ", s).strip().lower()

def _load_overrides():
    if not os.path.isfile(_OVERRIDES_PATH):
        return {"names": {}, "tags": {}}
    with open(_OVERRIDES_PATH, "r") as f:
        data = yaml.safe_load(f) or {}
    return {"names": data.get("names", {}), "tags": data.get("tags", {})}

_OVR = _load_overrides()

# Lightweight guardrail: allow only benign visual attributes
_ALLOWED_HINTS = {
    "red necktie", "long bright red necktie", "stovepipe hat",
    "powdered wig", "lapel pin", "round spectacles", "bow tie",
    "formal suit", "victorian suit", "royal regalia", "ermine cape",
    "crown nearby", "feathered quill", "monochrome palette",
}

def _safe_hint(s: str) -> str:
    # pass through if every comma-separated token is allowed
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if all(p in _ALLOWED_HINTS for p in parts):
        return ", " + ", ".join(parts) if parts else ""
    return ""  # drop anything outside the safe list

def person_prompt(name: str, year: Optional[str] = None, tags: Optional[Iterable[str]] = None):
    pos = BASE_POS.format(name=name)
    neg = BASE_NEG

    # Era hint
    eh = era_hint(year)
    if eh: pos += ", " + eh

    # Name override
    nkey = _canon(name)
    for key, cfg in (_OVR.get("names") or {}).items():
        if _canon(key) == nkey:
            pos += _safe_hint(cfg.get("add", ""))
            if cfg.get("neg"): neg += ", " + cfg["neg"]
            break

    # Tag overrides
    for t in (tags or []):
        cfg = (_OVR.get("tags") or {}).get(t)
        if cfg:
            pos += _safe_hint(cfg.get("add", ""))
            if cfg.get("neg"): neg += ", " + cfg["neg"]

    return pos, neg
