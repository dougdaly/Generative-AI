from __future__ import annotations

"""Deterministic Wikidata label/image helpers for public series posters.

Public-facing people posters must not render raw Wikidata QIDs such as Q23 or
localized fallback labels. This module resolves labels/images by stable QID and
uses multiple generic lookup paths:

1. Wikidata entity API
2. Wikidata Special:EntityData JSON
3. Direct Wikidata Query Service SPARQL, bypassing the project cache
4. The project's SPARQL client as a final fallback

There are no president-, monarch-, award-, or athlete-specific overrides here.
"""

from dataclasses import dataclass, field
import re
from typing import Iterable, Sequence
from urllib.parse import quote

import requests

from agentic_multimodal.schemas.entities import Person
from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL


_QID_RE = re.compile(r"^Q\d+$")
_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_WIKIDATA_ENTITYDATA = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
_WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
_USER_AGENT = "agentic-multimodal-demo/1.0 (series label resolver; contact: local-demo)"


@dataclass
class ResolutionDiagnostics:
    """Debug details for label/image resolution."""

    attempted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    resolved_labels: dict[str, str] = field(default_factory=dict)
    resolved_images: dict[str, str] = field(default_factory=dict)

    def add_error(self, source: str, exc: BaseException) -> None:
        self.errors.append(f"{source}: {type(exc).__name__}: {exc}")


def is_qid_like(value: object) -> bool:
    return isinstance(value, str) and _QID_RE.fullmatch(value.strip()) is not None


def deterministic_language(language: str | None) -> str:
    """Return one deterministic language code for poster labels."""
    if not language or "[AUTO_LANGUAGE]" in language:
        return "en"
    return str(language).split(",", 1)[0].strip() or "en"


def ensure_qid(value: str) -> str:
    """Accept either a bare QID or a full Wikidata entity URI."""
    return str(value).rsplit("/", 1)[-1]


def _value(binding: dict, key: str) -> str | None:
    value = binding.get(key)
    return value.get("value") if isinstance(value, dict) else None


def _unique_qids(qids: Iterable[str]) -> list[str]:
    clean_qids: list[str] = []
    seen: set[str] = set()
    for raw in qids:
        if raw is None:
            continue
        qid = ensure_qid(str(raw))
        if not is_qid_like(qid) or qid in seen:
            continue
        seen.add(qid)
        clean_qids.append(qid)
    return clean_qids


def _batches(values: Sequence[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield list(values[start : start + size])

def _label_from_labels(labels: dict | None, language: str) -> str | None:
    """Extract a deterministic display label from Wikidata labels.

    Accept only the requested language key or English key. Do not require the
    nested "language" field to match, because Wikidata can return labels like:

        {"en": {"value": "George Washington", "language": "mul", "for-language": "en"}}

    The dictionary key is what matters for our requested display language.
    """
    if not isinstance(labels, dict):
        return None

    lang = deterministic_language(language)

    for key in [lang, "en"]:
        raw = labels.get(key)

        if isinstance(raw, str):
            label = raw.strip()
        elif isinstance(raw, dict):
            label = str(raw.get("value") or raw.get("*") or "").strip()
        else:
            continue

        if label and not is_qid_like(label):
            return label

    return None

def _commons_file_url(filename: str | None) -> str | None:
    if not filename:
        return None
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + quote(filename.replace(" ", "_"))


def _blank_meta(qids: Iterable[str]) -> dict[str, dict[str, str | None]]:
    return {qid: {"label": None, "image_url": None} for qid in _unique_qids(qids)}


def _merge_meta(
    base: dict[str, dict[str, str | None]],
    incoming: dict[str, dict[str, str | None]],
    diagnostics: ResolutionDiagnostics | None = None,
) -> None:
    for qid, meta in incoming.items():
        if qid not in base:
            continue
        label = meta.get("label")
        image_url = meta.get("image_url")
        if label and not is_qid_like(label) and not base[qid].get("label"):
            base[qid]["label"] = label
            if diagnostics:
                diagnostics.resolved_labels[qid] = label
        if image_url and not base[qid].get("image_url"):
            base[qid]["image_url"] = image_url
            if diagnostics:
                diagnostics.resolved_images[qid] = image_url


def fetch_entity_labels_and_images_live(
    qids: Iterable[str],
    *,
    language: str = "en",
    timeout: int = 20,
    batch_size: int = 50,
) -> dict[str, dict[str, str | None]]:
    """Resolve labels/P18 images through Wikidata's wbgetentities API."""
    clean_qids = _unique_qids(qids)
    out = _blank_meta(clean_qids)
    if not clean_qids:
        return out

    lang = deterministic_language(language)

    for batch in _batches(clean_qids, batch_size):
        response = requests.get(
            _WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels|claims",
                "languages": lang,
                "languagefallback": 1,
                "format": "json",
                "formatversion": 2,
            },
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
        entities = payload.get("entities", {})

        for qid in batch:
            entity = entities.get(qid) or {}
            label = _label_from_labels(entity.get("labels"), lang)
            if label:
                out[qid]["label"] = label

            claims = entity.get("claims") or {}
            p18_claims = claims.get("P18") or []
            for claim in p18_claims:
                mainsnak = claim.get("mainsnak") or {}
                datavalue = mainsnak.get("datavalue") or {}
                filename = datavalue.get("value")
                image_url = _commons_file_url(filename) if isinstance(filename, str) else None
                if image_url:
                    out[qid]["image_url"] = image_url
                    break

    return out


def fetch_entity_labels_and_images_entitydata(
    qids: Iterable[str],
    *,
    language: str = "en",
    timeout: int = 20,
) -> dict[str, dict[str, str | None]]:
    """Resolve one entity at a time through Special:EntityData JSON.

    This is slower than wbgetentities but useful as an independent fallback when
    a wrapper, cache, or batch API path behaves unexpectedly.
    """
    clean_qids = _unique_qids(qids)
    out = _blank_meta(clean_qids)
    lang = deterministic_language(language)

    for qid in clean_qids:
        response = requests.get(
            _WIKIDATA_ENTITYDATA.format(qid=qid),
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
        entity = ((payload.get("entities") or {}).get(qid) or {})

        label = _label_from_labels(entity.get("labels"), lang)
        if label:
            out[qid]["label"] = label

        claims = entity.get("claims") or {}
        p18_claims = claims.get("P18") or []
        for claim in p18_claims:
            mainsnak = claim.get("mainsnak") or {}
            datavalue = mainsnak.get("datavalue") or {}
            filename = datavalue.get("value")
            image_url = _commons_file_url(filename) if isinstance(filename, str) else None
            if image_url:
                out[qid]["image_url"] = image_url
                break

    return out


def fetch_entity_labels_and_images_direct_sparql(
    qids: Iterable[str],
    *,
    language: str = "en",
    timeout: int = 30,
) -> dict[str, dict[str, str | None]]:
    """Resolve labels/images through Wikidata Query Service without project cache."""
    clean_qids = _unique_qids(qids)
    out = _blank_meta(clean_qids)
    if not clean_qids:
        return out

    lang = deterministic_language(language)
    values = " ".join(f"wd:{qid}" for qid in clean_qids)
    query = f"""
    SELECT ?person ?personLabel ?image WHERE {{
      VALUES ?person {{ {values} }}
      OPTIONAL {{
        ?person rdfs:label ?personLabel .
        FILTER(LANG(?personLabel) = "{lang}")
      }}
      OPTIONAL {{ ?person wdt:P18 ?image . }}
    }}
    """

    response = requests.get(
        _WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    rows = ((response.json().get("results") or {}).get("bindings") or [])

    for row in rows:
        uri = _value(row, "person")
        if not uri:
            continue
        qid = ensure_qid(uri)
        if qid not in out:
            continue
        label = _value(row, "personLabel")
        image = _value(row, "image")
        if label and not is_qid_like(label):
            out[qid]["label"] = label
        if image:
            out[qid]["image_url"] = image

    return out


def fetch_entity_labels_and_images_sparql(
    client: WikidataSPARQL,
    qids: Iterable[str],
    *,
    language: str = "en",
) -> dict[str, dict[str, str | None]]:
    """Resolve labels/images through the project's SPARQL client."""
    clean_qids = _unique_qids(qids)
    out = _blank_meta(clean_qids)
    if not clean_qids:
        return out

    lang = deterministic_language(language)
    values = " ".join(f"wd:{qid}" for qid in clean_qids)

    query = f"""
    # agentic_multimodal_series_entity_labels_v6_explicit_language
    SELECT ?person ?personLabel ?image WHERE {{
      VALUES ?person {{ {values} }}
      OPTIONAL {{
        ?person rdfs:label ?personLabel .
        FILTER(LANG(?personLabel) = "{lang}")
      }}
      OPTIONAL {{ ?person wdt:P18 ?image . }}
    }}
    """
    rows = client.run(query)

    for row in rows:
        uri = _value(row, "person")
        if not uri:
            continue
        qid = ensure_qid(uri)
        if qid not in out:
            continue
        label = _value(row, "personLabel")
        image = _value(row, "image")
        if label and not is_qid_like(label):
            out[qid]["label"] = label
        if image:
            out[qid]["image_url"] = image

    return out


def fetch_entity_labels_and_images(
    client: WikidataSPARQL | None,
    qids: Iterable[str],
    *,
    language: str = "en",
    prefer_live: bool = True,
    diagnostics: ResolutionDiagnostics | None = None,
) -> dict[str, dict[str, str | None]]:
    """Fetch deterministic labels/images by QID.

    The function tries multiple generic resolvers and merges the first good
    label/image for each QID. Exceptions are recorded in diagnostics instead of
    disappearing silently.
    """
    clean_qids = _unique_qids(qids)
    out = _blank_meta(clean_qids)
    if not clean_qids:
        return out

    diag = diagnostics

    sources = []
    if prefer_live:
        sources.extend([
            ("wikidata_api", lambda missing: fetch_entity_labels_and_images_live(missing, language=language)),
            ("entitydata_json", lambda missing: fetch_entity_labels_and_images_entitydata(missing, language=language)),
            ("direct_sparql", lambda missing: fetch_entity_labels_and_images_direct_sparql(missing, language=language)),
        ])
    else:
        sources.append(("direct_sparql", lambda missing: fetch_entity_labels_and_images_direct_sparql(missing, language=language)))

    if client is not None:
        sources.append(("project_sparql", lambda missing: fetch_entity_labels_and_images_sparql(client, missing, language=language)))

    for source_name, resolver in sources:
        missing = [
            qid
            for qid, meta in out.items()
            if not meta.get("label") or not meta.get("image_url")
        ]
        if not missing:
            break
        if diag:
            diag.attempted.append(source_name)
        try:
            meta = resolver(missing)
            _merge_meta(out, meta, diag)
        except Exception as exc:
            if diag:
                diag.add_error(source_name, exc)

    return out


def diagnose_entity_resolution(
    client: WikidataSPARQL | None,
    qids: Iterable[str],
    *,
    language: str = "en",
) -> dict[str, object]:
    """Return a notebook-friendly diagnostic payload for a few QIDs."""
    clean_qids = _unique_qids(qids)
    diagnostics = ResolutionDiagnostics()
    meta = fetch_entity_labels_and_images(
        client,
        clean_qids,
        language=language,
        prefer_live=True,
        diagnostics=diagnostics,
    )
    return {
        "qids": clean_qids,
        "attempted": diagnostics.attempted,
        "errors": diagnostics.errors,
        "meta": meta,
        "resolved_labels": diagnostics.resolved_labels,
        "resolved_images": diagnostics.resolved_images,
    }


def unresolved_people_labels(people: Iterable[Person]) -> list[Person]:
    """Return people whose display name is missing or still a raw QID."""
    out: list[Person] = []
    for person in people:
        name = getattr(person, "name", None)
        if not name or is_qid_like(str(name)):
            out.append(person)
    return out


def repair_people_labels_and_images(
    client: WikidataSPARQL | None,
    people: Iterable[Person],
    *,
    language: str = "en",
    prefer_live: bool = True,
    strict: bool = False,
) -> list[Person]:
    """Return people with deterministic labels/images repaired by stable QID.

    This generic cleanup pass is safe for positions, monarchs, awards, and
    future sports-award providers. With strict=True, unresolved labels raise an
    actionable error including resolver diagnostics.
    """
    people_list = list(people)
    qids = [getattr(person, "qid", None) for person in people_list if getattr(person, "qid", None)]
    diagnostics = ResolutionDiagnostics()
    meta_by_qid = fetch_entity_labels_and_images(
        client,
        qids,
        language=language,
        prefer_live=prefer_live,
        diagnostics=diagnostics,
    )

    fixed: list[Person] = []
    for person in people_list:
        qid = getattr(person, "qid", None)
        meta = meta_by_qid.get(qid, {}) if qid else {}
        current_name = getattr(person, "name", None)
        current_image = getattr(person, "image_url", None)

        repaired_name = meta.get("label") or current_name or qid or "Unknown person"
        repaired_image = meta.get("image_url") or current_image

        if hasattr(person, "model_copy"):
            fixed.append(person.model_copy(update={"name": repaired_name, "image_url": repaired_image}))
        elif hasattr(person, "copy"):
            fixed.append(person.copy(update={"name": repaired_name, "image_url": repaired_image}))
        else:
            fixed.append(
                Person(
                    qid=qid,
                    name=repaired_name,
                    image_url=repaired_image,
                    terms=getattr(person, "terms", []) or [],
                )
            )

    if strict:
        unresolved = unresolved_people_labels(fixed)
        if unresolved:
            unresolved_qids = [getattr(person, "qid", None) for person in unresolved]
            preview = "\n".join(
                f"- {getattr(person, 'qid', None)}: name={getattr(person, 'name', None)!r}"
                for person in unresolved[:20]
            )
            diag_payload = diagnose_entity_resolution(client, unresolved_qids[:10], language=language)
            raise RuntimeError(
                "Some Person records still have unresolved display labels after generic QID repair. "
                "Do not render a public poster with raw QIDs.\n"
                + preview
                + "\n\nResolver diagnostics:\n"
                + repr(diag_payload)
            )

    return fixed
