from __future__ import annotations
# Dedicated to cleaning up scanned & OCR'd text
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Any
import unicodedata
from dataclasses import dataclass
import re, unicodedata

_APOS = r"['\u2019]"  # if you normalize you can just use "'"

_WORD_RE  = re.compile(rf"[A-Za-z]+(?:{_APOS}[A-Za-z]+)?(?:-[A-Za-z]+(?:{_APOS}[A-Za-z]+)?)*")
_TOKEN_RE = re.compile(rf"[A-Za-z0-9]+(?:{_APOS}[A-Za-z0-9]+)?(?:-[A-Za-z0-9]+(?:{_APOS}[A-Za-z0-9]+)?)*")

_WEIRD_PUNCT_RE = re.compile(r"[^\w\s]{2,}")          # sequences like "&%", "—-", "??"
_PAGE_ID_RE = re.compile(r"(\d{1,5})")

_SHORT_OK = {
    "i","a","an","am","as","at","be","by","do","go","he","if","in","is","it",
    "me","my","no","of","on","or","so","to","up","us","we"
}
UNICODE_PUNCT_MAP = {
    "\u00A0": " ",      # NBSP
    "“": '"', "”": '"',
    "‘": "'", "’": "'",
    "…": "..."}

FORBIDDEN_GLYPHS = {
    "™": "", "®": "", "§": "",
    # I'd default to "flag-only" for £, €, ¥ unless you have a known mapping.
    "£": "",  # or leave as-is and only flag; see cfg below
    "€": "",
    "¥": "",
    "«": '', 
    "»": ''
}

_ALLOWED_RE = re.compile(r"^[\x09\x0A\x0D\x20-\x7E]*$")  # tabs/newlines + ASCII printable



def _page_id_from_path(p: Path) -> str:
    m = _PAGE_ID_RE.search(p.stem)
    return m.group(1).zfill(3) if m else p.stem


def _vowel_ratio(tok: str, vowels: str = "aeiou") -> float:
    v = set(vowels)
    letters = [c for c in tok.lower() if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c in v for c in letters) / len(letters)



def _is_suspicious_token(tok: str) -> bool:
    t = tok.lower()

    # allow common short words
    if len(t) <= 2:
        return t not in _SHORT_OK

    # repeated chars like "lll", "oooo"
    if re.search(r"(.)\1{2,}", t):
        return True

    # apostrophe weirdness
    if t.startswith("'") or t.endswith("'") or "''" in t:
        return True
    if t.count("'") > 1:
        return True

    # mixed digits and letters
    if re.search(r"[a-z].*\d|\d.*[a-z]", t):
        return True

    # low vowel ratio (treat y as vowel, and only apply to longer tokens)
    if len(t) >= 5 and _vowel_ratio(t, vowels="aeiouy") < 0.20:
        return True

    return False

REDACTION_RE = re.compile(r"(?i)\bx{4,}\b")

@dataclass(frozen=True)
class CleanupConfig:
    # text normalization
    normalize_unicode: bool = True
    # punctuation rules
    fix_amp_percent: bool = True
    fix_im_star: bool = True
    normalize_equals_dashes: bool = True
    normalize_dash_runs: bool = True
    normalize_double_hyphen: bool = True
    equals_between_wordchars_to_hyphen: bool = True
    remove_guillemets: bool = True
    fix_quote_zero: bool = True
    collapse_spaces: bool = True
    normalize_unicode_punct: bool = True
    replace_forbidden_glyphs: bool = True

@dataclass
class TextDiag:
    page_id: str
    kind: str
    details: dict[str, Any]

def _flag_non_ascii(s: str, *, page_id: str, diags: list[TextDiag]) -> None:
    # Report any non-ASCII printable chars (excluding newline/tab/carriage return)
    bad = sorted({ch for ch in s if ord(ch) > 0x7E or (ord(ch) < 0x20 and ch not in ("\n", "\t", "\r"))})
    if bad:
        diags.append(TextDiag(
            page_id=page_id,
            kind="non_ascii_or_control_chars",
            details={"chars": bad, "count": len(bad)},
        ))


def preprocess_text(s: str, cfg: CleanupConfig) -> str:
    if cfg.normalize_unicode:
        s = unicodedata.normalize("NFKC", s)
        s = (s.replace("\u2019", "'").replace("\u2018", "'")
               .replace("\u201c", '"').replace("\u201d", '"')
               .replace("\u2014", "-").replace("\u2013", "-"))

    if cfg.fix_amp_percent:
        s = re.sub(r"&\s*%", "&", s)

    if cfg.fix_im_star:
        s = re.sub(r"\bI\*m\b", "I'm", s)

    if cfg.normalize_equals_dashes:
        s = re.sub(r"\s*=\s*-{1,}\s*", " - ", s)        # =-- / =- -> -
        s = re.sub(r"\s*(?:=~|~=)\s*", " - ", s)        # =~ / ~= -> -

    if cfg.normalize_dash_runs:
        s = re.sub(r"-{7,}", " ... ", s)
        s = re.sub(r"-{3,}", " - ", s)                  # ------- -> -

    if cfg.normalize_double_hyphen:
        s = re.sub(r"\s*--\s*", " - ", s)               # -- -> -

    if cfg.equals_between_wordchars_to_hyphen:
        s = re.sub(r"(?<=\w)=(?=\w)", "-", s)           # moon=light -> moon-light

    if cfg.remove_guillemets:
        s = re.sub(r"«\s*»", " ... ", s)
        s = re.sub(r"(?<=\W)«(?=\W)", "", s)

    if cfg.fix_quote_zero:
        s = re.sub(r'"\s*0,', '" O,', s)

    if cfg.collapse_spaces:
        s = re.sub(r"[ \t]{2,}", " ", s)

    if cfg.normalize_unicode_punct:
        for a, b in UNICODE_PUNCT_MAP.items():
            s = s.replace(a, b)
    
    if cfg.replace_forbidden_glyphs:
        for ch, repl in FORBIDDEN_GLYPHS.items():
            if ch in s:
                s = s.replace(ch, repl)

    return s

import re

REDACTION_TOKENS = {"xxxxx", "xxxxxx", "xxxxxxx"}
REDACTION_RE = re.compile(
    rf"(?<!\w)(?:{'|'.join(map(re.escape, REDACTION_TOKENS))})(?!\w)",
    flags=re.I
)


from wordfreq import zipf_frequency
def is_probably_english(tok: str) -> bool:
    return tok.isalpha() and zipf_frequency(tok.lower(), "en") >= 3.0  # tune 2.5–4.0

token_map = {
    "4t":"it",
    "abnut": "about",
    "agoe": "ago.",
    "airection": "direction",
    "aman":"a man",
    "awey":"away",
    "begans": "begins",
    "birtheday":"birthday",
    "bndated":"undated",
    "couldn": "couldn't",
    "couldn't'": "couldn't",
    "dansl'ecole": "dans l'ecole",
    "desi four": "died four",
    "didntt": "didn't",
    "dontt": "don't",
    "dreppi":"dropping",
    "expres&ion":"expression",
    "forme": "for me",
    "givine":"divine",
    "gomething":"something",
    "goodenight":"good-night",
    "goes ome":"goes home",
    "inlove": "in love",
    "i'l]": "i'll",
    "knwwn": "known",
    "lewyer":"lawyer",
    "mand": "and",
    "with mee":"with me.",
    "mpsity":"university",
    "mre":"mr.",
    "mrse":"mrs.",
    "nbt":"not",
    "odiovs":"odious",
    "pine-epple":"pine-apple",
    "preath":"breath",
    "rounde":"round.",
    "siving":"giving",
    "sometwimes":"sometimes",
    "sowetimes":"sometimes",
    "tage":"see",
    "thaughts":"thoughts",
    "thovght":"thought",
    "toenight": "tonight",
    "toeday":"today",
    "ue's":"he's",
    "wallaee":"wallace",
    "whilee": "while",
    "xv\"": "",
    "yousve": "you've",
    "youtre": "you're",
}


def case_insensitive_remap(repl: str, matched: str) -> str:
    # Whole-string case patterns
    if matched.isupper():
        return repl.upper()
    if matched.islower():
        return repl.lower()
    if matched[:1].isupper() and matched[1:].islower():
        return repl[:1].upper() + repl[1:].lower()

    # Fallback: map case letter-by-letter (ignore punctuation/spaces)
    out = []
    m_letters = [c for c in matched if c.isalpha()]
    j = 0
    for c in repl:
        if c.isalpha() and j < len(m_letters):
            out.append(c.upper() if m_letters[j].isupper() else c.lower())
            j += 1
        else:
            out.append(c)
    return "".join(out)


def apply_token_map(text: str, token_map: dict[str, str]) -> str:
    '''Apply case-insensitive remap of text words.'''
    # protect redactions so they never change
    protected = {}
    def _protect(m: re.Match) -> str:
        key = f"__REDACT_{len(protected)}__"
        protected[key] = m.group(0)
        return key

    text = REDACTION_RE.sub(_protect, text)

    for src in sorted(token_map.keys(), key=len, reverse=True):
        dst = token_map[src]

        # Word-ish boundaries that work even when src has punctuation like "]"
        pat = re.compile(rf"(?<!\w){re.escape(src)}(?!\w)", flags=re.I)

        # Preserve the matched casing
        text = pat.sub(lambda m, dst=dst: case_insensitive_remap(dst, m.group(0)), text)

    for key, val in protected.items():
        text = text.replace(key, val)

    return text




def make_anchor_edit(text: str, old: str, new: str, *, left_n=18, right_n=18, reason="manual") -> dict:
    hits = [m.start() for m in re.finditer(re.escape(old), text)]
    if len(hits) != 1:
        raise ValueError(f"old not unique: {old!r} hits={len(hits)}")
    i = hits[0]
    left = text[max(0, i-left_n):i]
    right = text[i+len(old):min(len(text), i+len(old)+right_n)]
    return {"old": old, "new": new, "left": left, "right": right, "reason": reason, "confidence": 1.0}


# Apply manually-created rules to clean up text.
def apply_cleanup_rules(
    text_dir: str | Path,
    out_dir: str | Path,
    *,
    token_map: dict[str, str] = token_map,
    write_manifest: bool = True,
) -> dict[str, Any]:
    cfg = CleanupConfig()

    text_dir = Path(text_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(text_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No .txt files found in: {text_dir}")

    manifest = {"in_dir": str(text_dir), "out_dir": str(out_dir), "files": []}

    for fp in files:
        raw = fp.read_text(errors="replace")
        txt = preprocess_text(raw, cfg)
        txt = apply_token_map(txt, token_map)

        out_fp = out_dir / fp.name.replace("_ocr.txt", "_cleaned.txt")
        out_fp.write_text(txt, encoding="utf-8")

        manifest["files"].append({
            "in": str(fp),
            "out": str(out_fp),
            "n_chars_in": len(raw),
            "n_chars_out": len(txt),
        })

    if write_manifest:
        mpath = out_dir / "cleanup_manifest.json"
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(mpath)

    return manifest

# Apply stats on text files to see which text parts should be cleaned up.
def build_cleanup_candidates(
    text_dir: str | Path,
    *,
    out_path: str | Path | None = None,
    min_count: int = 2,
    top_k: int = 200,
    max_examples: int = 5,
    common_freq_threshold: int = 25,
) -> dict[str, Any]:
    """
    Scan OCR .txt files and produce a review report:
      - frequent suspicious tokens (with page ids + context)
      - weird punctuation sequences (like "&%")
      - suggestions (closest matches among frequent "common" tokens)

    Assumptions:
      - Each page has a separate .txt file.
      - Filename contains a page number somewhere (014, page_14, etc). If not, uses stem.

    Output:
      dict suitable for json dump; optionally written to out_path.
    """
    cfg = CleanupConfig()

    text_dir = Path(text_dir)
    files = sorted(text_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No .txt files found in: {text_dir}")

    # 1) Read texts, collect word/token counts + store per-page text for context extraction
    page_text: dict[str, str] = {}
    token_counts: Counter[str] = Counter()
    weird_punct_counts: Counter[str] = Counter()
    token_pages: dict[str, set[str]] = defaultdict(set)

    for fp in files:
        page_id = _page_id_from_path(fp)
        txt_raw = fp.read_text(errors="replace")
        txt = preprocess_text(txt_raw, cfg)
        for src, dst in token_map.items():
            txt = re.sub(rf"(?i)\b{re.escape(src)}\b", dst, txt)
        # punctuation sequences like "&%", "—-" show up a lot in OCR
        for m in _WEIRD_PUNCT_RE.finditer(txt):
            weird_punct_counts[m.group(0)] += 1

        # count tokens (we’ll focus mostly on words later)
        for m in _TOKEN_RE.finditer(txt):
            tok = m.group(0)
            token_counts[tok.lower()] += 1
            token_pages[tok.lower()].add(page_id)

    # 2) Build a "common token" set from your corpus itself (no external dict needed)
    #    These act as candidate correction targets.
    common_tokens = {t for t, c in token_counts.items() if c >= common_freq_threshold and t.isalpha()}

    def suggest(tok: str) -> list[str]:
        # suggestions only from tokens you already see frequently in your own corpus
        if not common_tokens:
            return []
        return get_close_matches(tok, sorted(common_tokens), n=3, cutoff=0.72)

    # 3) Extract contexts for candidates (sample a few occurrences)
    def contexts_for(tok: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        # word-boundary search to avoid “part-of-a-word” matches
        pat = re.compile(rf"(?i)\b{re.escape(tok)}\b")
        for pid, txt in page_text.items():
            for m in pat.finditer(txt):
                start = max(m.start() - 60, 0)
                end = min(m.end() + 60, len(txt))
                snippet = txt[start:end].replace("\n", " ")
                out.append({"page": pid, "context": snippet})
                if len(out) >= max_examples:
                    return out
        return out

    # 4) Choose suspicious tokens worth reviewing
    def _is_ok_apostrophe_word(tok: str) -> bool:
        t = tok.lower()

        # wouldn't, couldn't, didn't, isn't, etc.
        if re.fullmatch(rf"[a-z]+n[']t", t):
            return True

        # she's, I'm, we're, they've, he'll, I'd, etc.
        if re.fullmatch(rf"[a-z]+['](s|m|re|ve|ll|d)", t):
            return True

        # names like O'Neill, D'Artagnan (keep tight so junk doesn't slip through)
        if re.fullmatch(rf"[a-z]{{1,2}}['][a-z]+", t):
            return True

        return False

    def should_review_word(tok: str, cnt: int) -> bool:
        if tok in common_tokens:
            return False  # common in corpus => stop bothering me
        if _is_ok_apostrophe_word(tok):
            return False
        if _is_suspicious_token(tok):
            return True
        # suggestion-based review only for rare-ish tokens
        if cnt > 3:
            return False

        sugs = suggest(tok)
        if not sugs:
            return False

        # pick the most frequent suggestion in your corpus
        best = max(sugs, key=lambda s: token_counts.get(s, 0))
        best_cnt = token_counts.get(best, 0)

        # only if the "fix" is way more common than the "bad" token
        if best_cnt < 5 * cnt:
            return False

        # avoid dumb short-word traps like many->any/man
        if len(tok) <= 4:
            return False

        return True
    candidates = []
    for tok, cnt in token_counts.most_common():
        if tok in common_tokens:
            continue
        if cnt < min_count:
            break
        if tok.lower() in REDACTION_TOKENS or re.fullmatch(r"x{4,}", tok.lower()):
            continue

        # focus on alphabetic-ish tokens for word corrections, but keep a few junky ones too
        is_wordish = bool(_WORD_RE.fullmatch(tok))
        if is_wordish and is_probably_english(tok):
            continue
        suspicious = is_wordish and should_review_word(tok, cnt)
        if not suspicious:
            continue

        candidates.append({
            "token": tok,
            "count": cnt,
            "pages": sorted(token_pages.get(tok, [])),
            "is_wordish": is_wordish,
            "vowel_ratio": round(_vowel_ratio(tok), 3),
            "suggestions": suggest(tok) if is_wordish else [],
            "examples": contexts_for(tok) if is_wordish else [],
        })

        if len(candidates) >= top_k:
            break

    # 5) Punctuation sequences to review as regex cleanup rules
    weird_punct = [
        {"seq": seq, "count": cnt}
        for seq, cnt in weird_punct_counts.most_common(50)
        if cnt >= min_count
    ]

    report = {
        "meta": {
            "generated_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "text_dir": str(text_dir),
            "n_files": len(files),
            "min_count": min_count,
            "top_k": top_k,
            "common_freq_threshold": common_freq_threshold,
        },
        "candidates": candidates,
        "weird_punct": weird_punct,
    }

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return report

PAGE_NUM_RE = re.compile(r"(\d{1,5})")

def page_sort_key(p: Path):
    m = PAGE_NUM_RE.search(p.stem)
    return int(m.group(1)) if m else 10**9

def stitch_pages(clean_dir: str | Path, out_path: str | Path, pattern="*_cleaned.txt") -> str:
    clean_dir = Path(clean_dir)
    files = sorted(clean_dir.glob(pattern), key=page_sort_key)
    if not files:
        raise FileNotFoundError(f"No {pattern} files found in {clean_dir}")

    parts = []
    for fp in files:
        txt = fp.read_text(errors="replace")
        # light formatting: strip trailing whitespace, compress excessive blank lines
        txt = "\n".join(line.rstrip() for line in txt.splitlines()).strip()
        txt = re.sub(r"\n{4,}", "\n\n\n", txt)  # cap huge blank gaps

        m = PAGE_NUM_RE.search(fp.stem)
        page_label = f"Page {int(m.group(1)):02d}" if m else fp.stem

        parts.append(
            "\n".join([
                "========================",
                page_label,
                "========================",
                txt,
                "",  # trailing newline between pages
            ])
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return str(out_path)
