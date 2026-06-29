import re

_SPLIT_RE = re.compile(r"(?<=[\.;:])\s+|(?:\s+—\s+)|(?:\s+--\s+)", re.UNICODE)
_CONJ_SPLIT_RE = re.compile(r",\s+(and|but|while|because|so)\s+", re.IGNORECASE)

def split_clauses(text: str, min_words: int = 8):
    parts = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
    refined = []
    for p in parts:
        # optional secondary split on conjunctions if the part is long
        if len(p.split()) > 25:
            sub = _CONJ_SPLIT_RE.split(p)
            # sub includes conjunction tokens; recombine simply
            buf = ""
            for tok in sub:
                if tok.lower() in {"and","but","while","because","so"}:
                    buf += ", " + tok + " "
                else:
                    if buf:
                        refined.append((buf + tok).strip())
                        buf = ""
                    else:
                        refined.append(tok.strip())
        else:
            refined.append(p)

    # merge tiny fragments
    merged = []
    for c in refined:
        if merged and len(c.split()) < min_words:
            merged[-1] = (merged[-1] + " " + c).strip()
        else:
            merged.append(c)

    return merged

