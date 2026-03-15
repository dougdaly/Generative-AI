from __future__ import annotations
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer

def embed_texts(texts: List[str], model_name: str, batch_size: int = 64, normalize: bool = True) -> np.ndarray:
    model = SentenceTransformer(model_name)
    X = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=normalize,
        show_progress_bar=True,
    )
    return np.asarray(X, dtype=np.float32)

