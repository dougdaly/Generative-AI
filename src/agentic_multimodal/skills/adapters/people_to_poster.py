# skills/adapters/people_to_poster.py
import hashlib
from agentic_multimodal.schemas.entities import Person
from agentic_multimodal.schemas.artifacts import ImageAsset, PosterItem, PosterSpec
from typing import Iterable, List, Optional, Tuple


def _year_from_iso(s: str | None) -> str | None:
    if not s: return None
    s = s.lstrip("+")
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else None

def _y4(s: str | None) -> int:
    if not s: return 9999
    s = s.lstrip("+")
    return int(s[:4]) if s[:4].isdigit() else 9999

def _label_for_span(name: str, start: str | None, end: str | None) -> str:
    if start and end: return f"{name}\n{start} / {end}"
    if start and not end: return f"{name}\n{start}"
    return name

def _span_first_last_years(terms) -> Tuple[str | None, str | None]:
    years = []
    for t in terms:
        y1 = _year_from_iso(getattr(t, "start", None))
        y2 = _year_from_iso(getattr(t, "end", None))
        if y1: years.append(y1)
        if y2: years.append(y2)
    if not years: return (None, None)
    years.sort()
    return years[0], (years[-1] if len(years) > 1 else None)

def _award_year(terms) -> str | None:
    for t in terms:
        y = _year_from_iso(getattr(t, "start", None))
        if y: return y
    return None

def _hash_path(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]

def _asset_from_path(path: str) -> ImageAsset:
    from PIL import Image
    w, h = Image.open(path).size
    return ImageAsset(id=_hash_path(path), path=path, width=w, height=h)

def people_to_posterspec_per_person(people: List[Person], *, title: str, image_paths: Iterable[str], cols: int = 6) -> PosterSpec:
    """
    One tile per person (leaders collapse multiple terms to a single span; awards become year-only).
    `image_paths` must align with `people` order.
    """
    items: List[PosterItem] = []
    for p, path in zip(people, image_paths):
        # Decide leader vs award by inspecting terms
        # Heuristic: if ANY term has an end date, treat as leader span; else treat as award-year
        has_end = any(getattr(t, "end", None) for t in p.terms)
        if has_end:
            ys, ye = _span_first_last_years(p.terms)
            label = _label_for_span(p.name, ys, ye)
        else:
            y = _award_year(p.terms)
            label = _label_for_span(p.name, y, None)
        items.append(PosterItem(image=_asset_from_path(path), label=label))
    return PosterSpec(title=title, grid_cols=cols, items=items)

def people_to_posterspec_per_term(people: List[Person], *, title: str, image_paths: Iterable[str], cols: int = 6) -> PosterSpec:
    def _label(name: str, ys: Optional[str], ye: Optional[str]) -> str:
        if ys and ye:  return f"{name}\n{ys} – {ye}"
        if ys and not ye: return f"{name}\n{ys} – Present"
        return name

    # flatten all terms
    terms = []
    for p in people:
        for t in p.terms:
            ys = _y4(getattr(t, "start", None))
            ye = _y4(getattr(t, "end", None))   # None/endless -> 9999 (after one-year terms)
            terms.append((p.name, ys, ye))

    # key tweak: start ↑, then end ↑, then name
    terms.sort(key=lambda it: (it[1], it[2], it[0]))
    
    # zip with image_paths (which were generated in the same order from name_year_pairs)
    items = []
    for (path, (name, ys, ye)) in zip(image_paths, terms):
        items.append(PosterItem(image=_asset_from_path(path), label=_label(name, ys, ye)))

    return PosterSpec(title=title, grid_cols=cols, items=items)


def _year_from_iso(s: Optional[str]) -> Optional[str]:
    if not s: return None
    s = s.lstrip("+")
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else None

def name_year_pairs(
    people: List[Person],
    *,
    mode: str = "per_term",   # "per_term" | "per_person_auto"
) -> List[Tuple[str, Optional[str]]]:
    """
    Returns [(name, year_for_prompt), ...]
    - per_term: duplicate leaders per term; year = start or end if start missing.
    - per_person_auto: one entry per person.
        If any term has an end -> treat as leader and use earliest start.
        Else -> treat as award and use first available year.
    """
    pairs: List[Tuple[str, Optional[str]]] = []

    if mode == "per_term":
        pairs = []
        for p in people:
            for t in p.terms:
                y = _year_from_iso(getattr(t, "start", None)) or _year_from_iso(getattr(t, "end", None))
                pairs.append((p.name, y))
        # sort by year asc, then name (None years last)
        pairs.sort(key=lambda ny: ((ny[1] is None), ny[1] or "9999", ny[0]))
        return pairs
    
    if mode == "per_person_auto":
        for p in people:
            terms = getattr(p, "terms", [])
            has_end = any(getattr(t, "end", None) for t in terms)
            if has_end:
                # leader: use earliest start year across terms
                starts = [_year_from_iso(getattr(t, "start", None)) for t in terms]
                starts = [y for y in starts if y]
                y = min(starts) if starts else None
            else:
                # award: use first available year (usually term.start)
                y = None
                for t in terms:
                    y = _year_from_iso(getattr(t, "start", None)) or _year_from_iso(getattr(t, "end", None))
                    if y: break
            pairs.append((p.name, y))
        return pairs

    raise ValueError(f"unknown mode={mode!r}")
