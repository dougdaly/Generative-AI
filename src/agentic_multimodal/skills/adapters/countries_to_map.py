# skills/adapters/countries_to_map.py
from typing import Callable, Dict, Iterable, Optional, List, Tuple
from agentic_multimodal.schemas.entities import Country, Person
from agentic_multimodal.schemas.artifacts import MapMarker, MapSpec, ImageAsset
import hashlib

LabelFn = Callable[[Country, Optional[Person]], str]
ImageFn = Callable[[Country, Optional[Person]], Optional[ImageAsset]]

# --- add these small helpers near the top ---
def _as_name(p) -> str | None:
    if p is None:
        return None
    if hasattr(p, "name"):
        return getattr(p, "name", None)
    if isinstance(p, dict):
        return p.get("name") or p.get("label") or p.get("title")
    if isinstance(p, str):
        return p
    return None

def _as_image_url(p) -> str | None:
    if p is None:
        return None
    if hasattr(p, "image_url"):
        return getattr(p, "image_url", None)
    if isinstance(p, dict):
        # try common keys
        return p.get("image_url") or p.get("image") or p.get("thumb") or p.get("url")
    return None

# --- update defaults to use helpers ---
from types import SimpleNamespace

def label_country_plus_pick(c, p):
    if not p:
        return c.name
    # works for dict or object
    pick_name = getattr(p, "name", None) or p.get("label") if isinstance(p, dict) else None
    pick_name = pick_name or (p.get("name") if isinstance(p, dict) else None) or ""
    return f"{c.name}\n{pick_name}".strip()

def image_from_pick_url(c, p):
    if not p:
        return None
    # accept either object or dict
    url  = getattr(p, "image_url", None) or (p.get("image_url") if isinstance(p, dict) else None)
    path = getattr(p, "image_path", None) or (p.get("image_path") if isinstance(p, dict) else None)
    out = {}
    if path: out["path"] = path
    if url:  out["url"]  = url
    return out or None

def normalize_pick(p):
    """If you want everything to look like an object downstream."""
    if isinstance(p, dict):
        return SimpleNamespace(**p)
    return p


def _label_country_only(c: Country, p: Optional[Person]) -> str:
    return c.name

def _image_none(c: Country, p: Optional[Person]) -> None:
    return None

def image_from_flag_url(c: Country, p: Optional[Person]) -> Optional[ImageAsset]:
    if not getattr(c, "flag_svg_url", None):
        return None
    return ImageAsset(
        id=c.qid + "_flag", path="", width=0, height=0,
        meta={"source_url": c.flag_svg_url, "entity_qid": c.qid, "entity_name": c.name, "type": "flag"},
    )

def countries_to_mapspec(
    countries,
    *,
    title: str,
    region: str | None = None,
    picks: dict[str, object] | None = None,     # country_qid -> Person (or dict)
    label_fn = label_country_plus_pick,
    image_fn = image_from_pick_url,
    require_coords: bool = True,
):
    region = region or "custom"
    markers = []
    for c in countries:
        if require_coords and not c.capital_coords:
            continue

        # inside the loop that builds markers
        p = (picks or {}).get(c.qid)
        lon, lat = c.capital_coords if c.capital_coords else (None, None)
        label = label_fn(c, p) if label_fn else (c.name or "")

        img_meta_raw = image_fn(c, p) if image_fn else None

        # NEW normalization
        pick_path = None
        pick_url  = None
        if isinstance(img_meta_raw, dict):
            # accept {'path': ...} and/or {'url': ...}
            v = img_meta_raw.get("path")
            if isinstance(v, str) and v.strip():
                pick_path = v
            v = img_meta_raw.get("url")
            if isinstance(v, str) and v.strip():
                pick_url = v
        elif isinstance(img_meta_raw, str):
            # allow image_fn to return a bare path or url; treat as path if it looks local
            if img_meta_raw.startswith(("http://", "https://")):
                pick_url = img_meta_raw
            else:
                pick_path = img_meta_raw

        markers.append(MapMarker(
            lon=lon, lat=lat, label=label,
            meta={
                "country_qid": c.qid,
                "country_name": c.name,
                "capital_name": c.capital_name,
                "flag_url": c.flag_svg_url,
                "pick_qid": (p or {}).get("qid") if isinstance(p, dict) else getattr(p, "qid", None),
                "pick_label": (p or {}).get("label") if isinstance(p, dict) else getattr(p, "name", None),
                "pick_image_path": pick_path,   # string or None
                "pick_image_url":  pick_url,    # string or None
            }
        ))

    return MapSpec(
        title=title,
        region=region,
        markers=markers,
    )
