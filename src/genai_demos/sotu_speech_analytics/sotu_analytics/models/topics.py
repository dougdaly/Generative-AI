from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import CountVectorizer,  TfidfVectorizer, ENGLISH_STOP_WORDS

def fit_topics(X, k, random_state=0):
    X64 = np.asarray(X, dtype=np.float64)  # more stable math path
    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    labels = km.fit_predict(X64)
    return labels, km


def topic_labels_compact(topic_terms: Dict[int, List[str]], max_terms: int = 6) -> Dict[int, str]:
    out = {}
    for tid, terms in topic_terms.items():
        out[int(tid)] = ", ".join(terms[:max_terms])
    return out

def label_topics(texts: List[str], labels: np.ndarray, k: int, ngram_range=(1,2), top_terms: int = 12) -> Dict[int, List[str]]:
    stop_words = list(ENGLISH_STOP_WORDS.union({"ve","ll","mr","madam","president","america","american","people","tonight","thank"}))
    token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z']+\b"
    vec = CountVectorizer(stop_words=stop_words, ngram_range=ngram_range, min_df=2, max_df=0.6, token_pattern=token_pattern)
    V = vec.fit_transform(texts)
    terms = np.array(vec.get_feature_names_out())

    topic_terms: Dict[int, List[str]] = {}
    for t in range(k):
        idx = np.where(labels == t)[0]
        if len(idx) == 0:
            topic_terms[t] = []
            continue
        counts = V[idx].sum(axis=0).A1
        top_idx = counts.argsort()[::-1][:top_terms]
        topic_terms[t] = [terms[i] for i in top_idx if counts[i] > 0]
    return topic_terms


def ctfidf_terms(
    texts_norm,
    labels,
    top_terms=15,
    ngram_range=(1, 3),
    min_df=2,
    max_df=0.7,
    stop_words=None,
):
    """
    Returns dict: topic_id -> list[str] of distinctive n-grams using class-based TF-IDF.
    """
    labels = np.asarray(labels)
    k = int(labels.max()) + 1

    # Build one "document" per topic by concatenating its texts
    topic_docs = []
    for t in range(k):
        idx = np.where(labels == t)[0]
        joined = " ".join(texts_norm[i] for i in idx)
        topic_docs.append(joined)

    vec = TfidfVectorizer(
        ngram_range=ngram_range,
        min_df=min_df,
        max_df=max_df,
        stop_words=stop_words,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z']+\b",
    )
    X = vec.fit_transform(topic_docs)  # shape: (k, vocab)
    vocab = np.array(vec.get_feature_names_out())

    out = {}
    for t in range(k):
        row = X[t].toarray().ravel()
        top_idx = row.argsort()[::-1][:top_terms]
        out[int(t)] = vocab[top_idx].tolist()
    return out


def topic_shares(labels: np.ndarray, k: int) -> Dict[int, float]:
    n = len(labels)
    out = {}
    for t in range(k):
        out[t] = float((labels == t).sum() / n) if n else 0.0
    return out

