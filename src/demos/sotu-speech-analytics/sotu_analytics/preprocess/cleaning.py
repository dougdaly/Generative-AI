import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class CleaningLog:
    dropped_lines: int = 0
    stripped_speaker_prefixes: int = 0
    removed_stage_directions: int = 0
    applied_bracket_corrections: int = 0
    dysfluency_fixes: int = 0
    restart_dedupe_hits: int = 0

def clean_transcript(text: str, cfg: Dict) -> Tuple[str, CleaningLog]:
    log = CleaningLog()

    # Stage A: normalize newlines/whitespace
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]

    # Stage B: drop audience lines, strip speaker prefixes
    drop_prefixes = tuple(cfg["cleaning"]["drop_line_prefixes"])
    speaker_prefixes = cfg["cleaning"]["strip_speaker_prefixes"]

    kept: List[str] = []
    for ln in lines:
        if any(ln.upper().startswith(p.upper()) for p in drop_prefixes):
            log.dropped_lines += 1
            continue
        for sp in speaker_prefixes:
            if ln.upper().startswith(sp.upper()):
                ln = ln[len(sp):].strip()
                log.stripped_speaker_prefixes += 1
                break
        if ln:
            kept.append(ln)
    text = " ".join(kept)

    # Stage C: remove stage directions in () or [] when keyword matches
    if cfg["cleaning"].get("remove_stage_directions", True):
        kws = cfg["cleaning"]["stage_direction_keywords"]
        kw_re = re.compile(r"\b(" + "|".join(map(re.escape, kws)) + r")\b", re.I)

        def strip_stage(m):
            inner = m.group(1)
            if kw_re.search(inner):
                log.removed_stage_directions += 1
                return " "
            return m.group(0)

        text = re.sub(r"\(([^)]{0,120})\)", strip_stage, text)
        text = re.sub(r"\[([^\]]{0,120})\]", strip_stage, text)

    # Stage D: editorial corrections X [Y] -> Y
    if cfg["cleaning"].get("apply_bracket_corrections", True):
        corr = re.compile(r"\b([A-Za-z]+)\s*\[\s*([A-Za-z]+)\s*\]")
        (text, n) = corr.subn(r"\2", text)
        log.applied_bracket_corrections += n

    # Stage E: minimal dysfluency cleanup
    if cfg["cleaning"].get("minimal_dysfluency_cleanup", True):
        before = text
        text = text.replace("—", " ").replace("–", " ")
        # remove broken fragments like "poi- poisonous" => "poisonous"
        text = re.sub(r"\b[A-Za-z]{1,6}-\s+(?=[A-Za-z])", "", text)
        if text != before:
            log.dysfluency_fixes += 1

    # Stage E2: restart dedupe (very conservative)
    if cfg["cleaning"].get("restart_dedupe", True):
        before = text
        # remove immediate repeated short phrases: "to remind us ... to remind us"
        patt = re.compile(r"\b((?:[A-Za-z]+(?:\s+|$)){1,4})\s+(?:and\s+)?\1\b", re.I)
        for _ in range(3):
            text2 = patt.sub(r"\1", text)
            if text2 == text:
                break
            text = text2
            log.restart_dedupe_hits += 1
        if text != before:
            pass

    # Stage F: spacing cleanup
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return text, log

