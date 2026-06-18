import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import argparse
import json
from pathlib import Path
from collections import defaultdict
import warnings

import numpy as np
import yaml
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize

from sotu_analytics.models.embeddings import embed_texts
from sotu_analytics.models.topics import ctfidf_terms, topic_shares
from sotu_analytics.models.topic_label_llm import label_topics_with_llm  # expects year, texts, X, labels, km, ngram_terms_by_topic, model
from sotu_analytics.io.save_json import save_json, save_jsonl
from sotu_analytics.viz.timelines import plot_topic_timeline


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def repo_paths():
    here = Path(__file__).resolve()
    repo_root = here.parents[4]        # .../Generative-AI
    project_root = here.parents[1]     # .../src/demos/sotu-speech-analytics
    return repo_root, project_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, default=None, help="Years to include, e.g. --years 2012 2020 2024 2026")
    parser.add_argument("--k", type=int, default=None, help="Override number of topics (default from config)")
    parser.add_argument("--model", type=str, default="qwen2.5:14b-instruct-q4_K_M", help="Ollama model for labeling")
    args = parser.parse_args()

    REPO_ROOT, PROJECT_ROOT = repo_paths()

    cfg = yaml.safe_load((PROJECT_ROOT / "configs" / "v1.yaml").read_text(encoding="utf-8"))
    speeches = cfg["data"]["speeches"]
    # Build year -> speech dict
    speech_by_year = {}
    for s in speeches:
        y = int(s["year"])
        speech_by_year[y] = s

    cfg_years = sorted(speech_by_year.keys())
    years = args.years if args.years else cfg_years

    k = args.k if args.k is not None else int(cfg["topics"]["k"])

    # Load and concatenate chunks across years
    all_texts = []
    all_norm_texts = []
    all_meta = []   # keep year, chunk_id, chunk_index
    per_year_counts = defaultdict(int)

    for year in years:
        chunks_path = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "chunks" / f"{year}.jsonl"
        if not chunks_path.exists():
            raise FileNotFoundError(f"Missing chunks file: {chunks_path}")

        chunks = load_jsonl(chunks_path)
        # filter boilerplate for topic modeling
        chunks_nb = [c for c in chunks if not c.get("is_boilerplate", False)]

        for c in chunks_nb:
            all_texts.append(c["text"])
            all_norm_texts.append(c.get("text_norm", c["text"]))
            all_meta.append(
                {
                    "year": year,
                    "chunk_id": c["chunk_id"],
                    "chunk_index": c["chunk_index"],
                    "uses_guest_example": bool(c.get("uses_guest_example", False)),
                    "guest_count": int(c.get("guest_count", 0)),
                }
            )
        per_year_counts[year] = len(chunks_nb)

    print("Non-boilerplate chunk counts:", dict(per_year_counts))
    print("Total chunks for global clustering:", len(all_texts))

    # Embed all texts
    e_cfg = cfg["embeddings"]
    X = embed_texts(all_texts, e_cfg["model_name"], e_cfg["batch_size"], e_cfg["normalize"])
    X = np.nan_to_num(np.asarray(X, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)

    # Global clustering
    # For this data size, KMeans is stable and fast enough.
    # Also, suppress noisy sklearn matmul warnings if they appear in your env.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*encountered in matmul.*",
            category=RuntimeWarning,
            module=r"sklearn\.utils\.extmath",
        )
        km = KMeans(n_clusters=k, random_state=int(cfg["topics"]["random_state"]), n_init=10)
        labels = km.fit_predict(X)
    assert len(all_texts) == len(all_norm_texts) == len(all_meta) == len(labels)

    # N-gram terms for audit/debug (global)
    t_cfg = cfg["topics"]
    terms = ctfidf_terms(
        all_norm_texts,
        labels,
        top_terms=int(t_cfg["top_terms"]),
        ngram_range=tuple(t_cfg["ngram_range"]),  # consider (2,3) here for interpretability
        min_df=int(t_cfg.get("min_df", 2)),
        max_df=float(t_cfg.get("max_df", 0.7)),
        stop_words=t_cfg.get("stop_words", None),
    )

    # LLM labels (global)
    # Note: label_topics_with_llm currently takes a 'year' argument. For global, pass a sentinel.
    topic_labels = label_topics_with_llm(
        year=0,  # "global"
        texts=all_texts,
        X=X,
        labels=labels,
        km=km,
        ngram_terms_by_topic=terms,
        model=args.model,
        top_n=6,
    )

    # Write outputs
    out_dir = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "derived" / "topics_global"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save global topic labels + terms
    save_json(str(out_dir / "global_topic_terms.json"), terms)
    save_json(str(out_dir / "global_topic_labels_llm.json"), topic_labels)

    # Save per-chunk topic assignments with metadata
    rows = []
    for meta, lab in zip(all_meta, labels):
        rows.append(
            {
                **meta,
                "topic_id": int(lab),
            }
        )
    save_jsonl(str(out_dir / "global_chunk_topics.jsonl"), rows)

    # Per-year plots + shares
    fig_dir = REPO_ROOT / "assets" / "sotu-speech-analytics" / "reports" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    table_dir = REPO_ROOT / "assets" / "sotu-speech-analytics" / "reports" / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)

    # Build compact legend labels from LLM
    labels_compact = {t: topic_labels[str(t)]["label"] if str(t) in topic_labels else topic_labels[t]["label"] for t in range(k)}

    # Group labels per year in original chunk order
    labels_by_year = defaultdict(list)
    for meta, lab in zip(all_meta, labels):
        labels_by_year[meta["year"]].append(int(lab))

    # Save topic shares per year
    shares_by_year = {}
    for year in years:
        arr = np.array(labels_by_year[year], dtype=int)
        shares_by_year[year] = topic_shares(arr, k=k)

        fig_path = fig_dir / f"{year}_global_topic_timeline.png"
        plot_topic_timeline(
            labels_by_year[year],
            title=f"{year} SOTU global topic timeline (non-boilerplate chunks)",
            topic_labels=labels_compact,
            outfile=str(fig_path),
        )
        print("Saved:", fig_path)

    save_json(str(table_dir / "global_topic_shares_by_year.json"), shares_by_year)
    print("Saved:", table_dir / "global_topic_shares_by_year.json")
    print("Saved:", out_dir / "global_chunk_topics.jsonl")
    print("Saved:", out_dir / "global_topic_labels_llm.json")


if __name__ == "__main__":
    main()

