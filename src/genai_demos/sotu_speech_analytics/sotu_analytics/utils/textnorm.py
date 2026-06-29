from __future__ import annotations
# Normalize ONLY "special guest" names (e.g., "With us tonight is Alejandro Gonzalez.")
# Keep foreign leaders and other PERSON entities intact unless they appear in guest-intro sentences.

import re
from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional

import spacy

# Load once at module import time (fast enough; avoids repeated loads)
_NLP = None


# -----------------------------
# Config
# -----------------------------

# Guest-intro cues. These show up a lot in SOTU transcripts.
GUEST_CUE_PATTERNS = [
    r"\bwith us tonight\b",
    r"\bis here tonight\b",
    r"\bin the gallery\b",
    r"\bplease stand\b",
    r"\bjoin me in welcoming\b",
    r"\blet'?s welcome\b",
    r"\bthank you for being here\b",
    r"\bwe are glad to have you\b",
    r"\bwe're glad to have you\b",
]

_GUEST_CUE_RE = re.compile("|".join(GUEST_CUE_PATTERNS), flags=re.IGNORECASE)

# Basic word token extractor for name aliases
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

# Titles to ignore in names
_TITLE_TOKENS = {"mr", "mrs", "ms", "dr", "general", "sergeant", "captain", "officer"}


# -----------------------------
# spaCy loader (cached)
# -----------------------------
_NLP: Optional[spacy.language.Language] = None

def _get_nlp() -> spacy.language.Language:
    global _NLP
    if _NLP is None:
        # NER is what we need. Disable everything else.
        _NLP = spacy.load("en_core_web_sm", disable=["tagger", "lemmatizer", "parser"])
    return _NLP


# -----------------------------
# Helpers
# -----------------------------
def _split_sentences(text: str) -> List[str]:
    """
    Lightweight sentence split. Prefer using your existing split_sentences() if you have it;
    this is an internal fallback that avoids depending on your pipeline modules.
    """
    # Try spaCy sentencizer if available
    try:
        nlp = _get_nlp()
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
        doc = nlp(text)
        return [s.text.strip() for s in doc.sents if s.text.strip()]
    except Exception:
        # Fallback regex
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

def _extract_person_entities(text: str) -> List[str]:
    nlp = _get_nlp()
    doc = nlp(text)
    out: List[str] = []
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            s = ent.text.strip()
            if s and s not in out:
                out.append(s)
    return out

def _tokenize_name(name: str) -> List[str]:
    toks = [t for t in _WORD_RE.findall(name)]
    toks = [t for t in toks if t.lower() not in _TITLE_TOKENS]
    return toks

def _build_alias_map(full_names: List[str], placeholder_prefix="SPECIAL_GUEST") -> Dict[str, str]:
    """
    Build alias map that handles:
      - full name -> placeholder
      - first name -> same placeholder (only if unique among guest names)
      - last name  -> same placeholder (only if unique among guest names)
    """
    # Assign placeholders in order
    canonical: Dict[str, str] = {}
    for i, name in enumerate(full_names, start=1):
        canonical[name] = f"{placeholder_prefix}_{i}"

    # Count tokens across names to detect ambiguity
    token_counts: Dict[str, int] = {}
    split_names: List[Tuple[str, List[str]]] = []
    for full in full_names:
        toks = _tokenize_name(full)
        split_names.append((full, toks))
        for t in toks:
            token_counts[t.lower()] = token_counts.get(t.lower(), 0) + 1

    alias: Dict[str, str] = dict(canonical)
    for full, toks in split_names:
        if len(toks) >= 2:
            first, last = toks[0], toks[-1]
            if token_counts.get(first.lower(), 0) == 1:
                alias[first] = canonical[full]
            if token_counts.get(last.lower(), 0) == 1:
                alias[last] = canonical[full]
        elif len(toks) == 1:
            # single token name stays as itself; already covered by canonical
            pass

    return alias

def _replace_with_alias_map(text: str, alias_map: Dict[str, str]) -> str:
    """
    Replace keys in alias_map with placeholders, longest first.
    Handles possessives: "Megan's" -> "SPECIAL_GUEST_1's"
    """
    keys = sorted(alias_map.keys(), key=len, reverse=True)
    out = text
    for k in keys:
        repl = alias_map[k]
        out = re.sub(rf"\b{re.escape(k)}('s)\b", rf"{repl}\1", out)
        out = re.sub(rf"\b{re.escape(k)}\b", repl, out)
    return out

def _guest_intro_sentences(sentences: List[str]) -> List[str]:
    return [s for s in sentences if _GUEST_CUE_RE.search(s)]


# -----------------------------
# Public API
# -----------------------------
@dataclass
class GuestNormResult:
    text_norm: str
    guest_map: Dict[str, str]  # alias -> placeholder
    guest_canonical: Dict[str, str]  # full name -> placeholder
    flags: Dict[str, object]  # uses_guest_example, guest_count, matched_cues


def normalize_guests_only(text: str) -> GuestNormResult:
    """
    Normalize ONLY special-guest names (PERSON entities found in guest-intro sentences).
    Keeps all other PERSON entities (e.g., Putin, Maduro) untouched unless they appear in guest-intro sentences.

    Returns GuestNormResult with:
      - text_norm: modified text
      - guest_map: alias map used for replacement (full + first/last if unambiguous)
      - guest_canonical: mapping of full names -> placeholder
      - flags: metadata
    """
    sentences = _split_sentences(text)
    guest_sents = _guest_intro_sentences(sentences)

    # Extract guest PERSON entities only from guest-intro sentences
    guest_full_names: List[str] = []
    for s in guest_sents:
        for p in _extract_person_entities(s):
            if p not in guest_full_names:
                guest_full_names.append(p)

    if not guest_full_names:
        return GuestNormResult(
            text_norm=text,
            guest_map={},
            guest_canonical={},
            flags={
                "uses_guest_example": False,
                "guest_count": 0,
                "matched_cues": [],
            },
        )

    alias_map = _build_alias_map(guest_full_names, placeholder_prefix="SPECIAL_GUEST")
    canonical = {full: alias_map[full] for full in guest_full_names}

    text_norm = _replace_with_alias_map(text, alias_map)

    # Which cue patterns matched anywhere in the text (for debugging/audit)
    matched = [pat for pat in GUEST_CUE_PATTERNS if re.search(pat, text, flags=re.IGNORECASE)]

    return GuestNormResult(
        text_norm=text_norm,
        guest_map=alias_map,
        guest_canonical=canonical,
        flags={
            "uses_guest_example": True,
            "guest_count": len(guest_full_names),
            "matched_cues": matched,
        },
    )


def _get_nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("en_core_web_sm", disable=["tagger", "lemmatizer", "parser"])
        # NER is on by default in the model; no need for sentencizer here
    return _NLP

_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

def normalize_person_names(text: str) -> Tuple[str, Dict[str, str], Dict[str, bool]]:
    """
    Returns:
      text_norm: text with PERSON names replaced by SPECIAL_GUEST_#
      name_map: mapping from observed name/alias -> placeholder
      flags: metadata flags (uses_guest_example, guest_count)
    """
    nlp = _get_nlp()
    doc = nlp(text)

    # Collect PERSON entity strings in order of appearance
    persons: List[str] = []
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            s = ent.text.strip()
            if s and s not in persons:
                persons.append(s)

    # Assign placeholders in order
    canonical_map: Dict[str, str] = {}
    for i, name in enumerate(persons, start=1):
        canonical_map[name] = f"SPECIAL_GUEST_{i}"

    # Build alias map (first/last name) when safe
    # We'll only alias tokens that are unambiguous within this chunk.
    token_counts: Dict[str, int] = {}
    split_names = []

    for full in persons:
        toks = _WORD_RE.findall(full)
        toks = [t for t in toks if t.lower() not in {"mr", "mrs", "ms", "dr"}]
        split_names.append((full, toks))
        for t in toks:
            token_counts[t.lower()] = token_counts.get(t.lower(), 0) + 1

    alias_map: Dict[str, str] = dict(canonical_map)

    for full, toks in split_names:
        if len(toks) >= 2:
            first = toks[0]
            last = toks[-1]
            # Alias first/last only if unique among PERSON names in this chunk
            if token_counts.get(first.lower(), 0) == 1:
                alias_map[first] = canonical_map[full]
            if token_counts.get(last.lower(), 0) == 1:
                alias_map[last] = canonical_map[full]
        elif len(toks) == 1:
            # Single-token names (e.g., "Madonna") just map itself; already in canonical_map
            pass

    # Replace occurrences in text: do longest-first to avoid partial clobbering
    # Handle possessives: "Megan's" -> "SPECIAL_GUEST_1's"
    # Use word boundaries so we don't replace substrings inside other words.
    keys = sorted(alias_map.keys(), key=len, reverse=True)

    text_norm = text
    for k in keys:
        repl = alias_map[k]
        # Replace possessive first
        text_norm = re.sub(rf"\b{re.escape(k)}('s)\b", rf"{repl}\1", text_norm)
        # Then plain word
        text_norm = re.sub(rf"\b{re.escape(k)}\b", repl, text_norm)

    flags = {
        "uses_guest_example": len(persons) > 0,
        "guest_count": len(persons),
    }
    return text_norm, alias_map, flags


# -----------------------------
# Quick self-test (optional)
# -----------------------------
if __name__ == "__main__":
    sample = (
        "And America's armed forces defeated an enemy to end the reign of outlaw dictator Nicolas Maduro. "
        "We're working with Delcy Rodriguez. With us tonight is Alejandro Gonzalez. Alejandro, please stand."
    )
    res = normalize_guests_only(sample)
    print(res.text_norm)
    print(res.guest_canonical)
    print(res.flags)