from typing import Callable, Dict, Iterable, Optional, List, Tuple
from agentic_multimodal.schemas.entities import Country, Person
from agentic_multimodal.schemas.artifacts import MapMarker, MapSpec, ImageAsset
from agentic_multimodal.skills.data.wikimedia_cache import cache_flags_for_markers

import hashlib
from types import SimpleNamespace

LabelFn = Callable[[Country, Optional[Person]], str]
ImageFn = Callable[[Country, Optional[Person]], Optional[ImageAsset]]

_COUNTRY_SHORT_NAME_BY_QID = {
    # Reusable display aliases for map labels.
    # Use stable QIDs so this does not depend on source-language wording.
    "Q55": "Netherlands",
    "Q145": "United Kingdom",
    "Q142": "France",
    "Q183": "Germany",
    "Q38": "Italy",
    "Q29": "Spain",
    "Q45": "Portugal",
    "Q40": "Austria",
    "Q39": "Switzerland",
    "Q213": "Czechia",
}


def country_display_name(country: Country) -> str:
    """Return a compact display name for map labels.

    This does not change the source data. It only controls rendered labels.
    """
    qid = getattr(country, "qid", None)
    if qid in _COUNTRY_SHORT_NAME_BY_QID:
        return _COUNTRY_SHORT_NAME_BY_QID[qid]

    name = getattr(country, "name", "") or ""

    prefixes = [
        "Kingdom of the ",
        "Kingdom of ",
        "Republic of the ",
        "Republic of ",
        "Principality of ",
        "Grand Duchy of ",
    ]

    for prefix in prefixes:
        if name.startswith(prefix):
            return name[len(prefix):].strip()

    return name

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


def label_country_plus_pick(c, p):
    if not p:
        return c.name
    # works for dict or object
    pick_name = getattr(p, "name", None) or p.get("label") if isinstance(p, dict) else None
    pick_name = pick_name or (p.get("name") if isinstance(p, dict) else None) or ""
    return f"{country_display_name(c)}\n{pick_name}".strip()

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
    return country_display_name(c)

def _image_none(c: Country, p: Optional[Person]) -> None:
    return None

def image_from_flag_url(c: Country, p: Optional[Person]) -> Optional[ImageAsset]:
    if not getattr(c, "flag_svg_url", None):
        return None
    return ImageAsset(
        id=c.qid + "_flag", path="", width=0, height=0,
        meta={"source_url": c.flag_svg_url, "entity_qid": c.qid, "entity_name": c.name, "type": "flag"},
    )

def _rounded_coords(country: Country, digits: int = 3) -> tuple[float | None, float | None]:
    coords = getattr(country, "capital_coords", None)
    if not coords:
        return (None, None)

    lon, lat = coords
    return (round(float(lon), digits), round(float(lat), digits))


def _country_dedupe_key(country: Country) -> tuple:
    """Group duplicate country-like entities for map rendering."""
    return (
        country_display_name(country).casefold(),
        _rounded_coords(country),
    )


def _country_preference_key(country: Country) -> tuple:
    """Prefer compact/common country entities over long official wrapper entities."""
    source_name = getattr(country, "name", "") or ""
    display_name = country_display_name(country)

    official_prefixes = (
        "Kingdom of ",
        "Kingdom of the ",
        "Republic of ",
        "Republic of the ",
        "Principality of ",
        "Grand Duchy of ",
    )

    has_official_prefix = source_name.startswith(official_prefixes)

    # Lower is better.
    return (
        has_official_prefix,
        source_name != display_name,
        len(source_name),
        getattr(country, "qid", ""),
    )


def dedupe_countries_for_map(countries: Iterable[Country]) -> list[Country]:
    """Remove duplicate map entities after display-name normalization.

    Example: Q29999 "Kingdom of the Netherlands" and Q55 "Netherlands"
    both render as Netherlands at Amsterdam. Keep the compact entity.
    """
    best: dict[tuple, Country] = {}

    for country in countries:
        key = _country_dedupe_key(country)
        current = best.get(key)

        if current is None or _country_preference_key(country) < _country_preference_key(current):
            best[key] = country

    return sorted(
        best.values(),
        key=lambda c: (country_display_name(c).casefold(), getattr(c, "qid", "")),
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
    countries = dedupe_countries_for_map(countries)
    region = region or "custom"
    markers = []
    for c in countries:
        if require_coords and not c.capital_coords:
            continue

        display_country_name = country_display_name(c)

        p = (picks or {}).get(c.qid)
        lon, lat = c.capital_coords if c.capital_coords else (None, None)

        country_label = country_display_name(c)
        label = label_fn(c, p) if label_fn else country_label

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
                "capital_name": c.capital_name,
                "flag_url": c.flag_svg_url,
                "pick_qid": (p or {}).get("qid") if isinstance(p, dict) else getattr(p, "qid", None),
                "pick_label": (p or {}).get("label") if isinstance(p, dict) else getattr(p, "name", None),
                "pick_image_path": pick_path,   # string or None
                "pick_image_url":  pick_url,    # string or None
                "country_name": display_country_name,
                "country_source_name": c.name,
                "country_display_name": display_country_name,
            }
        ))

    return MapSpec(
        title=title,
        region=region,
        markers=markers,
    )
