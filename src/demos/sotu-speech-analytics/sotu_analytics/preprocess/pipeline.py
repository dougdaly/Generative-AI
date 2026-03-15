from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional
import re

from sotu_analytics.preprocess.cleaning import clean_transcript, CleaningLog
from sotu_analytics.preprocess.sentence_split import split_sentences
from sotu_analytics.preprocess.chunking import make_chunks
from sotu_analytics.utils.textnorm import normalize_guests_only


@dataclass
class PipelineLog:
    cleaning: Dict
    n_sentences: int
    n_chunks: int
    boilerplate_chunks: int
    boilerplate_reasons: Dict[str, int]


BOILER_START = re.compile(
    r"^(good (evening|night)\b|thank you\b|mr\. speaker\b|madam vice president\b|"
    r"vice president\b|members of congress\b|my fellow americans\b|my fellow citizens\b)",
    re.I,
)

FORMAL_PHRASES = re.compile(
    r"\b(mr\. speaker|madam vice president|vice president|members of congress|my fellow americans|my fellow citizens)\b",
    re.I,
)

def annotate_boilerplate_chunk(text: str):
    t = text.strip()
    wc = len(t.split())

    # pure greetings are boilerplate regardless
    if re.match(r"^(good (evening|night)|thank you)\b", t, re.I) and wc <= 12:
        return True, "ceremonial_opening"

    # formal address is boilerplate only when it's basically the whole chunk
    if BOILER_START.search(t) and wc <= 25:
        return True, "formal_address"

    # otherwise, not boilerplate
    return False, None


def clean_and_chunk(text: str, year: int, cfg: Dict) -> Tuple[Dict, List[Dict]]:
    clean_text, clean_log = clean_transcript(text, cfg)
    sentences = split_sentences(clean_text)

    ch_cfg = cfg["chunking"]
    chunks = make_chunks(
        sentences=sentences,
        year=year,
        sentences_per_chunk=ch_cfg["sentences_per_chunk"],
        overlap_sentences=ch_cfg["overlap_sentences"],
    )

    # annotate boilerplate
    bp_count = 0
    bp_reasons: Dict[str, int] = {}
    for c in chunks:
        is_bp, reason = annotate_boilerplate_chunk(c["text"])
        c["is_boilerplate"] = is_bp
        c["boilerplate_reason"] = reason
        if is_bp:
            bp_count += 1
            bp_reasons[reason] = bp_reasons.get(reason, 0) + 1
        norm = normalize_guests_only(c["text"])
        c["text_norm"] = norm.text_norm
        c["guest_map"] = norm.guest_canonical
        # keep your existing flag too; this one is more precise than boilerplate
        c["uses_guest_example"] = bool(norm.flags.get("uses_guest_example", False))
        c["guest_count"] = int(norm.flags.get("guest_count", 0))

    pipe_log = PipelineLog(
        cleaning=clean_log.__dict__,
        n_sentences=len(sentences),
        n_chunks=len(chunks),
        boilerplate_chunks=bp_count,
        boilerplate_reasons=bp_reasons,
    )
    clean_doc = {
        "year": year,
        "source_url": None,
        "clean_text": clean_text,
        "pipeline_log": asdict(pipe_log),
        "n_sentences": len(sentences),
        "n_chunks": len(chunks),
    }

    return clean_doc, chunks
