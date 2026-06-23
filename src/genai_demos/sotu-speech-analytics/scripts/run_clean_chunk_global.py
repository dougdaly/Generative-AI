import argparse
import json
from pathlib import Path
import yaml

from sotu_analytics.io.load_raw import load_text
from sotu_analytics.io.save_json import save_json, save_jsonl
from sotu_analytics.preprocess.pipeline import clean_and_chunk

def repo_paths():
    here = Path(__file__).resolve()
    repo_root = here.parents[4]
    project_root = here.parents[1]
    return repo_root, project_root

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    REPO_ROOT, PROJECT_ROOT = repo_paths()

    cfg_path = PROJECT_ROOT / "configs" / "v1.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    speeches = cfg["data"]["speeches"]
    # Build year -> speech dict
    speech_by_year = {}
    for s in speeches:
        y = int(s["year"])
        speech_by_year[y] = s

    cfg_years = sorted(speech_by_year.keys())
    years = args.years if args.years else cfg_years

    clean_dir = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "clean"
    chunks_dir = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "chunks"
    clean_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    summary = []

    for year in years:
        if year not in speech_by_year:
            summary.append({"year": year, "status": "missing_in_config"})
            continue

        raw_path = Path(speech_by_year[year]["raw_path"])
        if not raw_path.is_absolute():
            raw_path = REPO_ROOT / raw_path

        clean_path = clean_dir / f"{year}.json"
        chunks_path = chunks_dir / f"{year}.jsonl"

        if not raw_path.exists():
            summary.append({"year": year, "status": "missing_raw", "raw_path": str(raw_path)})
            continue

        if (not args.force) and clean_path.exists() and chunks_path.exists():
            # skip
            try:
                clean_doc = json.loads(clean_path.read_text(encoding="utf-8"))
                summary.append({
                    "year": year,
                    "status": "skipped",
                    "n_sentences": clean_doc.get("n_sentences"),
                    "n_chunks": clean_doc.get("n_chunks"),
                    "boilerplate_chunks": clean_doc.get("pipeline_log", {}).get("boilerplate_chunks"),
                })
            except Exception:
                summary.append({"year": year, "status": "skipped"})
            continue

        raw = load_text(str(raw_path))
        clean_doc, chunks = clean_and_chunk(raw, year=year, cfg=cfg)

        save_json(str(clean_path), clean_doc)
        save_jsonl(str(chunks_path), chunks)

        summary.append({
            "year": year,
            "status": "written",
            "n_sentences": clean_doc.get("n_sentences"),
            "n_chunks_total": len(chunks),
            "boilerplate_chunks": clean_doc.get("pipeline_log", {}).get("boilerplate_chunks"),
            "guest_chunks": sum(1 for c in chunks if c.get("uses_guest_example")),
            "guest_mentions": sum(int(c.get("guest_count", 0)) for c in chunks),
        })

        print(f"{year}: wrote clean/chunks")

    print("\nSummary:")
    for row in summary:
        print(row)

if __name__ == "__main__":
    main()
