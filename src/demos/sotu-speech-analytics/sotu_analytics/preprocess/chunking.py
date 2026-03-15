from typing import List, Dict

def make_chunks(
    sentences: List[str],
    year: int,
    sentences_per_chunk: int = 3,
    overlap_sentences: int = 1,
) -> List[Dict]:
    assert sentences_per_chunk > 0
    assert 0 <= overlap_sentences < sentences_per_chunk

    step = sentences_per_chunk - overlap_sentences
    chunks = []
    idx = 0
    chunk_index = 0
    while idx < len(sentences):
        window = sentences[idx : idx + sentences_per_chunk]
        if not window:
            break
        text = " ".join(window).strip()
        if text:
            chunks.append(
                {
                    "chunk_id": f"{year}_{chunk_index:04d}",
                    "year": year,
                    "chunk_index": chunk_index,
                    "text": text,
                }
            )
            chunk_index += 1
        idx += step
    return chunks

