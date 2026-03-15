import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import argparse
import json
from pathlib import Path
from collections import defaultdict
import time

import yaml

from sotu_analytics.io.save_json import save_json, save_jsonl

# You should have these:
# - build_rhetoric_prompt in sotu_analytics/prompts.py
# - ollama_generate_json in sotu_analytics/models/topic_label_llm.py (or wherever you kept it)
from sotu_analytics.prompts import build_rhetoric_prompt
from sotu_analytics.models.topic_label_llm import ollama_generate_json


def repo_paths():
    here = Path(__file__).resolve()
    repo_root = here.parents[4]        # .../Generative-AI
    project_root = here.parents[1]     # .../src/demos/sotu-speech-analytics
    return repo_root, project_root


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def index_chunks_by_id(chunks_rows):
    # chunk rows look like: {"chunk_id": "...", "year": 2024, "chunk_index": 0, "text": "...", ...}
    return {r["chunk_id"]: r for r in chunks_rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="qwen2.5:14b-instruct-q4_K_M")
    parser.add_argument("--years", nargs="+", type=int, default=None, help="Years to include, e.g. --years 2012 2020 2024 2026")
    parser.add_argument("--max_chunks", type=int, default=None, help="Optional cap for testing")
    parser.add_argument("--sleep", type=float, default=0.0, help="Optional sleep between calls (seconds)")
    parser.add_argument("--force", action="store_true", help="Overwrite output files instead of appending/resuming.")
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

    global_topics_path = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "derived" / "topics_global" / "global_chunk_topics.jsonl"
    if not global_topics_path.exists():
        raise FileNotFoundError(f"Missing: {global_topics_path}")

    global_rows = load_jsonl(global_topics_path)

    # Load per-year chunk text and index by chunk_id
    chunk_text_by_id = {}

    for year in years:
        chunks_path = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "chunks" / f"{year}.jsonl"
        if not chunks_path.exists():
            raise FileNotFoundError(f"Missing chunks for {year}: {chunks_path}")
        chunk_rows = load_jsonl(chunks_path)
        chunk_text_by_id.update(index_chunks_by_id(chunk_rows))

    # Output paths
    out_dir = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "derived" / "rhetoric"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "global_chunk_rhetoric.jsonl"
    summary_path = out_dir / "global_rhetoric_summary_counts.json"

    if args.force:
        if out_path.exists():
            out_path.unlink()
        if summary_path.exists():
            summary_path.unlink()

    # If rerunning, you may want to skip already-labeled chunks
    already = set()
    if (not args.force) and out_path.exists():
        for row in load_jsonl(out_path):
            # skip only successful rows
            if row.get("tone") is not None and ("error" not in row):
                already.add(row["chunk_id"])


    results = []
    tone_counts = defaultdict(int)           # (year, topic_id, tone) -> count
    device_counts = defaultdict(int)         # (year, topic_id, device) -> count

    # Optional cap
    rows_to_process = [r for r in global_rows if r["chunk_id"] not in already]
    if args.max_chunks:
        rows_to_process = rows_to_process[: args.max_chunks]

    print(f"Rows total: {len(global_rows)} | to label now: {len(rows_to_process)} | already labeled: {len(already)}")
    print("Years:", years)

    for i, meta in enumerate(rows_to_process, start=1):
        year = int(meta["year"])
        topic_id = int(meta["topic_id"])
        chunk_id = meta["chunk_id"]

        chunk = chunk_text_by_id.get(chunk_id)
        if not chunk:
            # skip with record
            rec = {**meta, "error": "missing_chunk_text"}
            results.append(rec)
            continue

        text = chunk.get("text", "")
        prompt = build_rhetoric_prompt(year, text)

        try:
            resp = ollama_generate_json(args.model, prompt, temperature=0.0, timeout=180)
            rec = {
                **meta,
                "tone": resp.get("tone"),
                "device": resp.get("device"),
                "target": resp.get("target"),
                "uses_guest_example_llm": resp.get("uses_guest_example"),
                "confidence": resp.get("confidence"),
                "evidence": resp.get("evidence", {}),
                "model": args.model,
            }
        except Exception as e:
            rec = {**meta, "error": str(e), "model": args.model}

        results.append(rec)

        # Update quick aggregates only for successful records
        if "error" not in rec:
            tone_counts[(year, topic_id, rec["tone"])] += 1
            device_counts[(year, topic_id, rec["device"])] += 1

        if args.sleep:
            time.sleep(args.sleep)

        if i % 20 == 0:
            print(f"Labeled {i}/{len(rows_to_process)}...")

    # Append to jsonl (do not overwrite existing unless you want to)
    mode = "a" if out_path.exists() else "w"
    with out_path.open(mode, encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Save summary counts (easy to plot later)
    summary = {
        "tone_counts": [
            {"year": y, "topic_id": t, "tone": tone, "count": c}
            for (y, t, tone), c in tone_counts.items()
        ],
        "device_counts": [
            {"year": y, "topic_id": t, "device": dev, "count": c}
            for (y, t, dev), c in device_counts.items()
        ],
    }
    save_json(str(summary_path), summary)

    print("Wrote:", out_path)
    print("Wrote:", str(summary_path))


if __name__ == "__main__":
    main()

