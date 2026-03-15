from __future__ import annotations
from typing import List

def split_sentences(text: str) -> List[str]:
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm", disable=["tagger", "ner", "lemmatizer"])
        nlp.add_pipe("sentencizer")
        doc = nlp(text)
        sents = [s.text.strip() for s in doc.sents]
        return [s for s in sents if s]
    except Exception:
        # STUB-lite fallback: regex split. Not perfect, but works in a pinch.
        import re
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

