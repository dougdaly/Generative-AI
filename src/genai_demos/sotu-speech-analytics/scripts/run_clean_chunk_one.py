import argparse

import yaml
from pathlib import Path
import argparse

from sotu_analytics.io.load_raw import load_text
from sotu_analytics.io.save_json import save_json, save_jsonl
from sotu_analytics.preprocess.pipeline import clean_and_chunk

def main():
    # Resolve project root (…/src/demos/sotu-speech-analytics)
    HERE = Path(__file__).resolve()
    REPO_ROOT = HERE.parents[4]        # .../Generative-AI
    PROJECT_ROOT = HERE.parents[1]     # .../src/demos/sotu-speech-analytics
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True, help="Year to include, e.g. --year 2024")
    args = parser.parse_args()
    year = args.year

    cfg_path = PROJECT_ROOT / "configs" / "v1.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    # If your config raw_path is relative, interpret it from PROJECT_ROOT
    speech = [s for s in cfg["data"]["speeches"] if s["year"] == year][0]
    year = speech["year"]

    raw_path = REPO_ROOT / speech["raw_path"]
    raw = load_text(str(raw_path))

    clean_doc, chunks = clean_and_chunk(raw, year, cfg)
    clean_doc["source_url"] = speech["source_url"]

    # Write outputs to assets/ relative to PROJECT_ROOT
    out_clean = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "clean" / f"{year}.json"
    out_chunks = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "chunks" / f"{year}.jsonl"

    save_json(str(out_clean), clean_doc)
    save_jsonl(str(out_chunks), chunks)

    print("Config:", cfg_path)
    print("Raw:", raw_path)
    print("Cleaning log:", clean_doc["pipeline_log"]["cleaning"])
    print("Sentences:", clean_doc.get("n_sentences"), "Chunks:", clean_doc.get("n_chunks"))
    print("Boilerplate:", clean_doc.get("pipeline_log", {}).get("boilerplate_chunks"))
    print("Pipeline log:", clean_doc["pipeline_log"])
    print("First chunk:", chunks[0]["text"][:240])

if __name__ == "__main__":
    main()

