# SOTU Speech Analytics Quickstart

This quickstart is for public reviewers who want to understand the SOTU speech analytics demo without first running larger model workflows.

## Demo map

- Overview notebook: `notebooks/sotu-speech-analytics/00_sotu_speech_analytics_overview.ipynb`
- Reusable source code: `src/demos/sotu-speech-analytics`
- Supporting assets and generated outputs: `assets/sotu-speech-analytics`

The overview notebook is the intended notebook entry point. The previous zero-byte notebook placeholders in `notebooks/sotu-speech-analytics` are not part of the runnable public path.

## What this demo shows

The demo analyzes State of the Union speech text with a reproducible layout:

- raw speech transcripts and processed data under `assets/sotu-speech-analytics/data`
- reusable Python modules and runner scripts under `src/demos/sotu-speech-analytics`
- generated figures, tables, and narrative output under `assets/sotu-speech-analytics/reports`
- an overview notebook that explains the workflow and links the artifacts together

The lightweight review path is CPU-only. Some full workflow steps may use embedding models, topic modeling, LLM labeling, API keys, or larger dependency downloads depending on which scripts or notebook cells are run.

## CPU-only smoke test

From the repository root, run:

```bash
python - <<'PY'
from pathlib import Path
from collections import Counter
import re

asset_dir = Path("assets/sotu-speech-analytics")

if not asset_dir.exists():
    raise SystemExit(f"Missing expected asset directory: {asset_dir}")

text_files = list(asset_dir.rglob("*.txt")) + list(asset_dir.rglob("*.md"))

print(f"Found {len(text_files)} text-like files under {asset_dir}")

if not text_files:
    print("No .txt or .md files found. Open the overview notebook for the demo workflow.")
    raise SystemExit(0)

sample_path = text_files[0]
text = sample_path.read_text(encoding="utf-8", errors="ignore")

tokens = re.findall(r"[A-Za-z']+", text.lower())
counts = Counter(tokens)

print(f"Sample file: {sample_path}")
print(f"Token count: {len(tokens):,}")
print("Top terms:")
for word, count in counts.most_common(20):
    print(f"{word:>20}  {count}")
PY
```

This confirms that the asset path exists and that basic text inspection can run with only the Python standard library.

## Review path

1. Open `notebooks/sotu-speech-analytics/00_sotu_speech_analytics_overview.ipynb` for the narrative overview.
2. Inspect `src/demos/sotu-speech-analytics` for the reusable package, configuration, and runner scripts.
3. Inspect `assets/sotu-speech-analytics` for transcripts, cleaned data, derived outputs, figures, tables, and reports.
4. Run the CPU-only smoke test above before attempting any heavier notebook or model-backed steps.

## Notes on heavier steps

The source tree includes scripts for preprocessing, topic modeling, rhetoric analysis, and report generation. Those steps are separate from this quickstart. Review their configuration before running them, because model-backed stages may require non-standard dependencies, API access, or more compute than a basic CPU-only environment.
# SOTU Speech Analytics — Minimal Quickstart

Location: notebooks/sotu-speech-analytics/

Overview
- A set of notebooks to analyze State-of-the-Union (SOTU) speeches.
- Current repository contains placeholder notebooks (00_quickstart.ipynb ... 05_graphs.ipynb). Files appear empty; implement or populate before expecting outputs.

Minimal local steps
1. Environment:
   conda env create -f environment_min.yml
   conda activate genai
   or pip install -r requirements.txt
2. Open the quickstart:
   - Open notebooks/sotu-speech-analytics/00_quickstart.ipynb in Jupyter or VS Code.
3. Data:
   - Notebooks do not include speech transcripts. Place any local SOTU transcripts in a data/ or notebooks/sotu-speech-analytics/data/ directory and update paths in the notebook.
   - Do not commit private or licensed transcripts.
4. Expected flow (what to add/implement)
   - 00_quickstart.ipynb: run end-to-end pipeline example (load transcript, basic preprocessing)
   - 01_clean_and_chunk.ipynb: text cleaning and chunking for RAG
   - 02_topics.ipynb: topic modeling / LDA or embedding-based clustering
   - 03_moves.ipynb: rhetorical move detection (labels)
   - 04_metrics_and_coalitions.ipynb: compute metrics and coalition analysis
   - 05_graphs.ipynb: visualization and network graphs

Caveats
- Notebooks are placeholders; implement code and provide data paths before running.
- Sensitive data should not be stored in the repository.
