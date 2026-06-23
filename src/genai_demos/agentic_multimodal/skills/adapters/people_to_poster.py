# skills/adapters/people_to_poster.py
"""
Adapter layer: turn a list of Person objects + generated portrait image paths
into a PosterSpec used by the renderer.

This module does NOT generate images. It only:
- formats labels (name + years)
- chooses whether we show one tile per person OR one tile per term
- converts file paths into ImageAsset objects (with stable IDs + dimensions)

Why it exists:
- keeps rendering concerns separate from data retrieval and SDXL generation
- gives us deterministic label formatting across posters
"""

import hashlib
import re
from typing import Iterable, List, Optional, Tuple

from agentic_multimodal.schemas.entities import Person
from agentic_multimodal.schemas.artifacts import ImageAsset, PosterItem, PosterSpec

_QID = re.compile(r"^Q\d+$")  # safety check: Wikidata IDs sometimes leak as display names


# ----------------------------
# Year parsing helpers
# ----------------------------
def _year_from_iso(s: str | None) -> str | None:
    """
    Extract a 4-digit year from Wikidata ISO-ish strings.
    Examples:
      "+1963-01-01T00:00:00Z" -> "1963"
      "2009-..."              -> "2009"
      None / junk             -> None

    We use this for *display* years and prompt hints.
    """
    if not s:
        return None
    s = s.lstrip("+")
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else None


def _y4(s: str | None) -> int:
    """
    Sort key version of year parsing.
    Returns a real year int when possible, otherwise a far-future sentinel.

    Why:
    - sorting wants numbers
    - display wants None when year is unknown
    """
    if not s:
        return 9999
    s = s.lstrip("+")
    return int(s[:4]) if s[:4].isdigit() else 9999


def _disp_year(y: str | int | None) -> str | None:
    """
    Convert our "year-ish" value into a printable year.
    Drops sentinel years (9999...) so open-ended terms show as "Name" not "Name 9999 –".
    """
    if y is None:
        return None
    y = str(y)
    if not y or y.startswith("9999"):
        return None
    return y


def _label_for_span(name: str, start_y: str | int | None, end_y: str | int | None) -> str:
    """
    Label format for leaders / office-holders:
      "Name\\nstart – end"
      "Name\\nstart –"    (open-ended term)
      "Name"              (no usable years)

    Newlines are intentional. Renderer prints label under the portrait.
    """
    s = _disp_year(start_y)
    e = _disp_year(end_y)
    if s and e:
        return f"{name}\n{s} – {e}"
    if s and not e:
        return f"{name}\n{s} –"
    return name


def _span_first_last_years(terms) -> Tuple[str | None, str | None]:
    """
    For multi-term leaders, compute earliest and latest year across all terms.
    Output is strings for display. Sorting is done elsewhere when needed.
    """
    years = []
    for t in terms:
        y1 = _year_from_iso(getattr(t, "start", None))
        y2 = _year_from_iso(getattr(t, "end", None))
        if y1:
            years.append(y1)
        if y2:
            years.append(y2)

    if not years:
        return (None, None)

    years.sort()
    return years[0], (years[-1] if len(years) > 1 else None)


def _award_year(terms) -> str | None:
    """
    For awards, we typically store the award year as term.start.
    If multiple terms exist, we take the first year we can find.
    """
    for t in terms:
        y = _year_from_iso(getattr(t, "start", None))
        if y:
            return y
    return None


def _label_for_award(name: str, year: str | None) -> str:
    """
    Label format for awards:
      "Name\\nYYYY"
      or just "Name" if year is unknown
    """
    return f"{name}\n{year}" if year else name


# ----------------------------
# Image asset helpers
# ----------------------------
def _hash_path(path: str) -> str:
    """
    Generate a stable short ID for an image based on file contents.
    Useful for caching and for consistent artifact IDs across runs.
    """
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _asset_from_path(path: str) -> ImageAsset:
    """
    Convert an image file into an ImageAsset with dimensions.
    Renderer relies on width/height for layout decisions.
    """
    from PIL import Image

    w, h = Image.open(path).size
    return ImageAsset(id=_hash_path(path), path=path, width=w, height=h)


# ----------------------------
# PosterSpec builders
# ----------------------------
def people_to_posterspec_per_person(
    people: List[Person],
    *,
    title: str,
    image_paths: Iterable[str],
    cols: int = 6,
) -> PosterSpec:
    """
    One poster tile per *person*.

    Label logic is "auto":
    - if any term has an end year -> treat as leader; show span (start–end)
    - else -> treat as award; show single year

    Assumes image_paths is aligned to people order.
    """
    items: List[PosterItem] = []
    for p, path in zip(people, image_paths):
        has_end = any(getattr(t, "end", None) for t in p.terms)

        if has_end:
            ys, ye = _span_first_last_years(p.terms)
            label = _label_for_span(p.name, ys, ye)
        else:
            y = _award_year(p.terms)
            label = _label_for_award(p.name, y)

        items.append(PosterItem(image=_asset_from_path(path), label=label))

    return PosterSpec(title=title, grid_cols=cols, items=items)


def people_to_posterspec_per_term(
    people: List[Person],
    *,
    title: str,
    image_paths: Iterable[str],
    cols: int = 6,
) -> PosterSpec:
    """
    One poster tile per *term* (duplicates people with multiple terms).
    Useful for posters like "All U.S. presidents by term".

    Implementation:
    - flatten every (person, term) into a sortable list
    - sort by start year then end year then name
    - zip the sorted term list to image_paths

    Assumes image_paths length matches flattened term count.
    """
    terms = []
    for p in people:
        for t in p.terms:
            ys_i = _y4(getattr(t, "start", None))
            ye_i = _y4(getattr(t, "end", None))
            ys_s = _year_from_iso(getattr(t, "start", None))
            ye_s = _year_from_iso(getattr(t, "end", None))
            terms.append((p.name, ys_i, ye_i, ys_s, ye_s))

    # Sort by start ↑, end ↑, then name for stable layout ordering
    terms.sort(key=lambda it: (it[1], it[2], it[0]))

    items = []
    for path, (name, _ys_i, _ye_i, ys_s, ye_s) in zip(image_paths, terms):
        items.append(PosterItem(image=_asset_from_path(path), label=_label_for_span(name, ys_s, ye_s)))

    return PosterSpec(title=title, grid_cols=cols, items=items)


# ----------------------------
# Prompt-pair helpers (used upstream during image generation)
# ----------------------------
def name_year_pairs_per_term(people: list[Person]) -> list[tuple[str, str | None]]:
    """
    Expand people into (display_name, year_hint) pairs, one entry per term.

    Why this exists:
    - SDXL prompts often benefit from a year hint for era styling ("1912 portrait photo")
    - terms provide the best per-tile year anchor

    Also does two safety things:
    - if a person name looks like a raw QID, fall back to p.qid
    - de-duplicate exact duplicate spans
    """
    pairs: list[tuple[str, str | None, str | None, str | None]] = []
    for p in people:
        display = p.name if p.name and not _QID.fullmatch(p.name) else p.qid
        for t in p.terms:
            y = _year_from_iso(t.start) or _year_from_iso(t.end)
            pairs.append((display, y, t.start, t.end))

    # stable sort: start asc then end asc; None treated as far future
    pairs.sort(key=lambda r: (r[2] or "9999-12-31", r[3] or "9999-12-31", r[0]))

    # remove exact duplicates (same name and same start/end span)
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
    mode: str = "per_term",  # "per_term" | "per_person_auto"
) -> List[Tuple[str, Optional[str]]]:
    """
    Produce [(name_for_prompt, year_hint), ...] used upstream when generating portraits.

    Modes:
    - per_term:
        One entry per term. People with multiple terms appear multiple times.
        Year hint is term.start (or term.end if start missing).
        Sorted for stable layout and reproducible batching.
    - per_person_auto:
        One entry per person.
        If any term has an end year -> treat as leader; year hint is earliest start.
        Else treat as award; year hint is first available year.
    """
    if mode == "per_term":
        pairs = []
        for p in people:
            for t in p.terms:
                y = _year_from_iso(getattr(t, "start", None)) or _year_from_iso(getattr(t, "end", None))
                pairs.append((p.name, y))
        pairs.sort(key=lambda ny: ((ny[1] is None), ny[1] or "9999", ny[0]))
        return pairs

    if mode == "per_person_auto":
        pairs: List[Tuple[str, Optional[str]]] = []
        for p in people:
            terms = getattr(p, "terms", [])
            has_end = any(getattr(t, "end", None) for t in terms)

            if has_end:
                # leader: use earliest start year across terms
                starts = [_year_from_iso(getattr(t, "start", None)) for t in terms]
                starts = [y for y in starts if y]
                y = min(starts) if starts else None
            else:
                # award: use first available year
                y = None
                for t in terms:
                    y = _year_from_iso(getattr(t, "start", None)) or _year_from_iso(getattr(t, "end", None))
                    if y:
                        break

            pairs.append((p.name, y))
        return pairs

    raise ValueError(f"unknown mode={mode!r}")
