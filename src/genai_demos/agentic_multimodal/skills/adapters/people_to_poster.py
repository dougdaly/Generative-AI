# skills/adapters/people_to_poster.py
"""
Adapter layer for people/award/office series posters.

This module has two layers:

1. Legacy helpers that build PosterSpec from Person objects plus aligned image paths.
   These are kept for backward compatibility with earlier notebooks.

2. Generic SeriesRecord helpers. These are the safer public-demo API because they
   join images by stable keys instead of relying on sorted directory order.

The renderer stays generic. This module owns series-specific label formatting,
record ordering, and conversion into PosterSpec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Tuple

from agentic_multimodal.schemas.entities import Person
from agentic_multimodal.schemas.artifacts import ImageAsset, PosterItem, PosterSpec

_QID = re.compile(r"^Q\d+$")
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.:-]+")


# ----------------------------
# Year/date parsing helpers
# ----------------------------
def _year_from_iso(s: str | None) -> str | None:
    """
    Extract a 4-digit year from Wikidata ISO-ish strings.

    Examples:
      "+1963-01-01T00:00:00Z" -> "1963"
      "2009-..."              -> "2009"
      None / junk              -> None
    """
    if not s:
        return None
    s = str(s).lstrip("+")
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else None


def _date_sort_value(s: str | None) -> str:
    """Full-date sort key. Missing dates sort last."""
    if not s:
        return "9999-12-31"
    return str(s).lstrip("+")


def _y4(s: str | None) -> int:
    if not s:
        return 9999
    s = str(s).lstrip("+")
    return int(s[:4]) if len(s) >= 4 and s[:4].isdigit() else 9999


def _disp_year(y: str | int | None) -> str | None:
    if y is None:
        return None
    y = str(y)
    if not y or y.startswith("9999"):
        return None
    return y


def _label_for_span(name: str, start_y: str | int | None, end_y: str | int | None) -> str:
    s = _disp_year(start_y)
    e = _disp_year(end_y)
    if s and e:
        return f"{name}\n{s} - {e}"
    if s and not e:
        return f"{name}\n{s}"
    return name


def _span_first_last_years(terms) -> Tuple[str | None, str | None]:
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
    for t in terms:
        y = _year_from_iso(getattr(t, "start", None))
        if y:
            return y
    return None


def _award_years(terms) -> list[str]:
    years: list[str] = []
    for t in terms:
        y = _year_from_iso(getattr(t, "start", None)) or _year_from_iso(getattr(t, "end", None))
        if y and y not in years:
            years.append(y)
    return sorted(years)


def _label_for_award(name: str, year: str | None) -> str:
    return f"{name}\n{year}" if year else name


def _safe_record_piece(value: str | None) -> str:
    value = value or "missing"
    value = _SAFE_ID.sub("_", str(value).strip())
    return value.strip("_") or "missing"


def _person_display_name(p: Person) -> str:
    name = getattr(p, "name", None)
    qid = getattr(p, "qid", None)
    if name and not _QID.fullmatch(str(name)):
        return str(name)
    if qid:
        return str(qid)
    return "Unknown person"


def _person_entity_id(p: Person) -> str:
    qid = getattr(p, "qid", None)
    if qid:
        return str(qid)
    return _safe_record_piece(_person_display_name(p)).lower()


# ----------------------------
# Image asset helpers
# ----------------------------
def _hash_path(path: str | Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _asset_from_path(path: str | Path) -> ImageAsset:
    from PIL import Image

    path = str(path)
    w, h = Image.open(path).size
    return ImageAsset(id=_hash_path(path), path=path, width=w, height=h)


# ----------------------------
# Generic series record contract
# ----------------------------
@dataclass(frozen=True)
class SeriesRecord:
    """One renderable tile in a people/award/office series poster.

    entity_id is the stable source entity, usually a Wikidata QID.
    record_id is the stable tile key. It differs from entity_id when a person
    appears more than once, for example Grover Cleveland or repeat award winners.
    image_key controls image reuse. By default, repeated terms reuse the same
    entity-level portrait.
    """

    series_key: str
    record_id: str
    entity_id: str
    image_key: str
    display_name: str
    subtitle: str | None
    sort_key: tuple[str, str, str]
    year_hint: str | None = None
    image_url: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.display_name}\n{self.subtitle}" if self.subtitle else self.display_name




def find_unresolved_series_labels(records: Iterable[SeriesRecord]) -> list[SeriesRecord]:
    """Return records whose display label still looks like a raw entity ID."""
    unresolved: list[SeriesRecord] = []
    for record in records:
        if _QID.fullmatch(str(record.display_name or "")):
            unresolved.append(record)
    return unresolved


def assert_series_labels_resolved(records: Iterable[SeriesRecord]) -> None:
    """Fail loudly before rendering a public poster with QID labels."""
    unresolved = find_unresolved_series_labels(records)
    if unresolved:
        preview = "\n".join(
            f"- {record.entity_id}: display_name={record.display_name!r}, record_id={record.record_id}"
            for record in unresolved[:20]
        )
        raise RuntimeError(
            "Some series records still have unresolved display labels. "
            "This usually means the provider label query or its cache is stale. "
            "Do not render a public poster with raw QIDs.\n"
            + preview
        )


def _subtitle_for_person_auto(terms) -> tuple[str | None, str | None]:
    """Return (subtitle, year_hint) for one tile per person."""
    terms = list(terms or [])
    has_end = any(getattr(t, "end", None) for t in terms)

    if has_end:
        ys, ye = _span_first_last_years(terms)
        if ys and ye:
            return f"{ys} - {ye}", ys
        if ys:
            return ys, ys
        return None, None

    years = _award_years(terms)
    if not years:
        return None, None
    if len(years) == 1:
        return years[0], years[0]
    if len(years) <= 3:
        return ", ".join(years), years[0]
    return f"{years[0]} - {years[-1]} ({len(years)}x)", years[0]


def people_to_series_records(
    people: List[Person],
    *,
    series_key: str,
    mode: str = "per_term",  # "per_term" | "per_person_auto"
    image_scope: str = "entity",  # "entity" | "record"
) -> list[SeriesRecord]:
    """Convert source Person objects into generic, ordered poster records.

    This is intentionally not POTUS-specific. The same contract works for office
    holders, monarchs, Nobel laureates, sports-award winners, and similar series.
    """
    if image_scope not in {"entity", "record"}:
        raise ValueError(f"unknown image_scope={image_scope!r}")

    records: list[SeriesRecord] = []

    if mode == "per_term":
        for p in people:
            display_name = _person_display_name(p)
            entity_id = _person_entity_id(p)
            terms = list(getattr(p, "terms", []) or [])

            if not terms:
                record_id = f"{series_key}:{entity_id}:noterm"
                image_key = entity_id if image_scope == "entity" else record_id
                records.append(
                    SeriesRecord(
                        series_key=series_key,
                        record_id=record_id,
                        entity_id=entity_id,
                        image_key=image_key,
                        display_name=display_name,
                        subtitle=None,
                        sort_key=("9999-12-31", "9999-12-31", display_name),
                        year_hint=None,
                        image_url=getattr(p, "image_url", None),
                        metadata={"mode": mode},
                    )
                )
                continue

            seen_spans: set[tuple[str, str]] = set()
            for idx, term in enumerate(terms):
                start = getattr(term, "start", None)
                end = getattr(term, "end", None)
                span_key = (str(start or ""), str(end or ""))
                if span_key in seen_spans:
                    continue
                seen_spans.add(span_key)
                start_year = _year_from_iso(start)
                end_year = _year_from_iso(end)
                year_hint = start_year or end_year

                if end_year:
                    subtitle = f"{start_year} - {end_year}" if start_year else end_year
                else:
                    subtitle = start_year

                record_id = ":".join(
                    [
                        _safe_record_piece(series_key),
                        _safe_record_piece(entity_id),
                        _safe_record_piece(start),
                        _safe_record_piece(end),
                        str(idx),
                    ]
                )
                image_key = entity_id if image_scope == "entity" else record_id
                records.append(
                    SeriesRecord(
                        series_key=series_key,
                        record_id=record_id,
                        entity_id=entity_id,
                        image_key=image_key,
                        display_name=display_name,
                        subtitle=subtitle,
                        sort_key=(_date_sort_value(start), _date_sort_value(end), display_name),
                        year_hint=year_hint,
                        image_url=getattr(p, "image_url", None),
                        metadata={"mode": mode, "term_index": idx, "start": start, "end": end},
                    )
                )

        records.sort(key=lambda r: r.sort_key)
        return records

    if mode == "per_person_auto":
        for p in people:
            display_name = _person_display_name(p)
            entity_id = _person_entity_id(p)
            terms = list(getattr(p, "terms", []) or [])
            starts = [_date_sort_value(getattr(t, "start", None)) for t in terms]
            ends = [_date_sort_value(getattr(t, "end", None)) for t in terms]
            earliest = min(starts) if starts else "9999-12-31"
            earliest_end = min(ends) if ends else "9999-12-31"
            subtitle, year_hint = _subtitle_for_person_auto(terms)
            record_id = f"{_safe_record_piece(series_key)}:{_safe_record_piece(entity_id)}:person"
            image_key = entity_id if image_scope == "entity" else record_id
            records.append(
                SeriesRecord(
                    series_key=series_key,
                    record_id=record_id,
                    entity_id=entity_id,
                    image_key=image_key,
                    display_name=display_name,
                    subtitle=subtitle,
                    sort_key=(earliest, earliest_end, display_name),
                    year_hint=year_hint,
                    image_url=getattr(p, "image_url", None),
                    metadata={"mode": mode, "term_count": len(terms)},
                )
            )

        records.sort(key=lambda r: r.sort_key)
        return records

    raise ValueError(f"unknown mode={mode!r}")


def series_records_to_prompt_items(records: Iterable[SeriesRecord]) -> list[dict[str, Any]]:
    """Build one prompt item per unique image_key, preserving first-seen order."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if record.image_key in seen:
            continue
        seen.add(record.image_key)
        out.append(
            {
                "image_key": record.image_key,
                "name": record.display_name,
                "year": record.year_hint,
                "ref_url": record.image_url,
                "record_id": record.record_id,
                "entity_id": record.entity_id,
            }
        )
    return out


def series_records_to_posterspec(
    records: Iterable[SeriesRecord],
    *,
    title: str,
    image_assets: Mapping[str, ImageAsset | str | Path],
    cols: int = 6,
) -> PosterSpec:
    """Build PosterSpec by joining records to images by stable image_key."""
    items: list[PosterItem] = []
    missing: list[SeriesRecord] = []

    for record in records:
        raw_asset = image_assets.get(record.image_key)
        if raw_asset is None:
            missing.append(record)
            continue

        if isinstance(raw_asset, ImageAsset):
            asset = raw_asset
        else:
            asset = _asset_from_path(raw_asset)

        items.append(PosterItem(image=asset, label=record.label))

    if missing:
        preview = "\n".join(
            f"- {r.image_key}: {r.display_name} ({r.record_id})" for r in missing[:20]
        )
        raise RuntimeError(
            f"Missing image assets for {len(missing)} series records.\n{preview}"
        )

    return PosterSpec(title=title, grid_cols=cols, items=items)


# ----------------------------
# Legacy PosterSpec builders
# ----------------------------
def people_to_posterspec_per_person(
    people: List[Person],
    *,
    title: str,
    image_paths: Iterable[str],
    cols: int = 6,
) -> PosterSpec:
    """Backward-compatible helper. Assumes image_paths is aligned to people order."""
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
    """Backward-compatible helper. Assumes image_paths is aligned to sorted terms."""
    terms = []
    for p in people:
        for t in p.terms:
            start = getattr(t, "start", None)
            end = getattr(t, "end", None)
            ys_i = _y4(start)
            ye_i = _y4(end)
            ys_s = _year_from_iso(start)
            ye_s = _year_from_iso(end)
            terms.append((p.name, ys_i, ye_i, _date_sort_value(start), _date_sort_value(end), ys_s, ye_s))

    terms.sort(key=lambda it: (it[3], it[4], it[0]))

    items = []
    for path, (name, _ys_i, _ye_i, _start_sort, _end_sort, ys_s, ye_s) in zip(image_paths, terms):
        items.append(PosterItem(image=_asset_from_path(path), label=_label_for_span(name, ys_s, ye_s)))

    return PosterSpec(title=title, grid_cols=cols, items=items)


# ----------------------------
# Prompt-pair helpers
# ----------------------------
def name_year_pairs_per_term(people: list[Person]) -> list[tuple[str, str | None]]:
    records = people_to_series_records(people, series_key="series", mode="per_term")
    return [(record.display_name, record.year_hint) for record in records]


def name_year_pairs(
    people: List[Person],
    *,
    mode: str = "per_term",
) -> List[Tuple[str, Optional[str]]]:
    records = people_to_series_records(people, series_key="series", mode=mode)
    return [(record.display_name, record.year_hint) for record in records]
