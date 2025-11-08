# skills/adapters/people_to_poster.py
import hashlib
from agentic_multimodal.schemas.entities import Person
from agentic_multimodal.schemas.artifacts import ImageAsset, PosterItem, PosterSpec
from typing import Iterable, List, Optional, Tuple

import re
_QID = re.compile(r"^Q\d+$")

def _year_from_iso(s: str | None) -> str | None:
    if not s: return None
    s = s.lstrip("+")
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else None

def _y4(s: str | None) -> int:
    if not s: return 9999
    s = s.lstrip("+")
    return int(s[:4]) if s[:4].isdigit() else 9999

def _disp_year(y: str | int | None) -> str | None:
    if y is None: return None
    y = str(y)
    if not y or y.startswith("9999"):  # treat as open-ended
        return None
    return y

# Replace your old _label_for_span with this:
def _label_for_span(name: str, start_y: str | int | None, end_y: str | int | None) -> str:
    s = _disp_year(start_y)
    e = _disp_year(end_y)
    if s and e:    return f"{name}\n{s} – {e}"
    if s and not e:return f"{name}\n{s} –"
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

def _label_for_award(name: str, year: str | None) -> str:
    return f"{name}\n{year}" if year else name


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
    items: List[PosterItem] = []
    for p, path in zip(people, image_paths):
        has_end = any(getattr(t, "end", None) for t in p.terms)
        if has_end:
            ys, ye = _span_first_last_years(p.terms)   # strings
            label = _label_for_span(p.name, ys, ye)    # keeps en-dash for leaders
        else:
            y = _award_year(p.terms)                   # year string
            label = _label_for_award(p.name, y)        # ← no trailing dash
        items.append(PosterItem(image=_asset_from_path(path), label=label))
    return PosterSpec(title=title, grid_cols=cols, items=items)



def people_to_posterspec_per_term(people: List[Person], *, title: str, image_paths: Iterable[str], cols: int = 6) -> PosterSpec:
    # Flatten all terms with both sort fields (ints) and display fields (strings)
    terms = []
    for p in people:
        for t in p.terms:
            # sort keys (ints with 9999 sentinel)
            ys_i = _y4(getattr(t, "start", None))
            ye_i = _y4(getattr(t, "end", None))
            # display years (strings; no sentinel)
            ys_s = _year_from_iso(getattr(t, "start", None))
            ye_s = _year_from_iso(getattr(t, "end", None))
            terms.append((p.name, ys_i, ye_i, ys_s, ye_s))

    # sort by start ↑, then end ↑, then name
    terms.sort(key=lambda it: (it[1], it[2], it[0]))

    # Build items using display years only
    items = []
    for path, (name, _ys_i, _ye_i, ys_s, ye_s) in zip(image_paths, terms):
        items.append(PosterItem(image=_asset_from_path(path), label=_label_for_span(name, ys_s, ye_s)))

    return PosterSpec(title=title, grid_cols=cols, items=items)


def name_year_pairs_per_term(people: list[Person]) -> list[tuple[str, str | None]]:
    pairs: list[tuple[str, str | None, str | None, str | None]] = []
    for p in people:
        # final safety: never surface a QID-looking name
        display = p.name if p.name and not _QID.fullmatch(p.name) else p.qid
        for t in p.terms:
            y = _year_from_iso(t.start) or _year_from_iso(t.end)
            pairs.append((display, y, t.start, t.end))
    # stable sort: start asc, then end asc; None treated as far future
    pairs.sort(key=lambda r: (r[2] or "9999-12-31", r[3] or "9999-12-31", r[0]))
    # drop exact duplicates (same name, same span); order is preserved
    uniq = []
    seen = set()
    for n, y, s, e in pairs:
        key = (n, s or "", e or "")
        if key in seen: 
            continue
        seen.add(key)
        uniq.append((n, y))
    return uniq


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
