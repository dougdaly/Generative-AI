import json
from pathlib import Path
import yaml
from collections import defaultdict
import argparse

from sotu_analytics.models.embeddings import embed_texts
from sotu_analytics.models.topics import fit_topics, label_topics, topic_shares
from sotu_analytics.io.save_json import save_json, save_jsonl
from sotu_analytics.viz.timelines import plot_topic_timeline
from sotu_analytics.models.topic_label_llm import label_topics_with_llm

import numpy as np
import warnings
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def load_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def main():
    HERE = Path(__file__).resolve()
    REPO_ROOT = HERE.parents[4]
    PROJECT_ROOT = HERE.parents[1]
    out_dir = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "derived" / "topics"

    cfg = yaml.safe_load((PROJECT_ROOT / "configs" / "v1.yaml").read_text(encoding="utf-8"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    year = args.year

    # Perform chunking
    chunks_path = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "chunks" / f"{year}.jsonl"
    chunks = load_jsonl(str(chunks_path))
        # filter boilerplate for topic modeling
    chunks_for_topics = [c for c in chunks if not c.get("is_boilerplate", False)]
    texts = [c["text"] for c in chunks_for_topics]

    # Embed texts 
    e_cfg = cfg["embeddings"]
    X = embed_texts(texts, e_cfg["model_name"], e_cfg["batch_size"], e_cfg["normalize"])
    X = np.nan_to_num(np.asarray(X, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)

    # fit topics -- labels and cluster centers (for LLM labeling)
    t_cfg = cfg["topics"]
    k = t_cfg["k"]
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*encountered in matmul.*",
            category=RuntimeWarning,
            module=r"sklearn\.utils\.extmath",
        )
        labels, km = fit_topics(X, k=k, random_state=t_cfg["random_state"])
    raw = np.asarray(km.cluster_centers_, dtype=np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    centroids = raw / norms
    centroids = np.nan_to_num(centroids, nan=0.0, posinf=0.0, neginf=0.0)

    model = "qwen2.5:14b-instruct-q4_K_M"
    topic_labels = {}
    texts_norm = [c.get("text_norm", c["text"]) for c in chunks_for_topics]
    terms = label_topics(texts_norm, labels, k=k, ngram_range=tuple(t_cfg["ngram_range"]), top_terms=t_cfg["top_terms"])
    topic_labels = label_topics_with_llm(
        year=year,
        texts=texts,
        X=X,
        labels=labels,
        km=km,
        ngram_terms_by_topic=terms,
        model="qwen2.5:14b-instruct-q4_K_M",
        top_n=6,
    )

    # build reverse map
    rev = defaultdict(list)
    for tid, rec in topic_labels.items():
        rev[rec["label"]].append(tid)

    dupes = {lbl: tids for lbl, tids in rev.items() if len(tids) > 1}

    save_json(str(out_dir / f"{year}_topic_labels_llm.json"), topic_labels)

    # 3) Legend labels: use LLM labels
    labels_compact = {t: topic_labels[t]["label"] for t in range(k)}

    legend_path = REPO_ROOT / "assets" / "sotu-speech-analytics" / "reports" / "tables" / f"{year}_topic_legend.tsv"
    legend_path.parent.mkdir(parents=True, exist_ok=True)

    with open(legend_path, "w", encoding="utf-8") as f:
        f.write("topic_id\tlabel\tconfidence\tkeywords\n")
        for tid in range(k):
            rec = topic_labels[tid]
            kws = ", ".join(rec.get("keywords", [])[:6])
            f.write(f"{tid}\t{rec.get('label')}\t{rec.get('confidence')}\t{kws}\n")

    print("Legend saved:", legend_path)
    print("Legend preview:")
    for tid in sorted(labels_compact.keys()):
        print(f"  {tid}: {labels_compact[tid]}")

    shares = topic_shares(labels, k=k)

    # attach topic_id back to the filtered chunks, and also build a mapping by chunk_id
    topic_rows = []
    for c, lab in zip(chunks_for_topics, labels):
        topic_rows.append({"chunk_id": c["chunk_id"], "topic_id": int(lab)})

    save_json(str(out_dir / f"{year}_topic_terms.json"), terms)
    save_json(str(out_dir / f"{year}_topic_shares.json"), shares)
    save_jsonl(str(out_dir / f"{year}_chunk_topics.jsonl"), topic_rows)

    # timeline plot (filtered, so index is "non-boilerplate chunk index")
    fig_path = REPO_ROOT / "assets" / "sotu-speech-analytics" / "reports" / "figures" / f"{year}_topic_timeline.png"
    plot_topic_timeline(
        [int(x) for x in labels],
        f"{year} SOTU topic timeline (non-boilerplate chunks)",
        topic_labels=labels_compact,
        outfile=str(fig_path),
    )

    print("Saved:", fig_path)
    print("Top terms per topic (first 3 topics):")
    for t in range(min(3, k)):
        print(t, terms.get(t, [])[:8])

    # validation
    for t in range(k):
        print(t, labels_compact[t], " | ngrams:", ", ".join(topic_labels[t]["ngram_terms"][:6]))


if __name__ == "__main__":
    main()

