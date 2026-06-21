# SOTU Speech Analytics Quickstart

This quickstart provides a lightweight way to inspect the SOTU speech analytics demo without running large models, downloading heavy assets, or requiring a GPU.

The full demo lives in:

- `notebooks/sotu-speech-analytics/00_sotu_speech_analytics_overview.ipynb`
- `src/demos/sotu-speech-analytics`
- `assets/sotu-speech-analytics`

## What this demo is meant to show

The SOTU speech analytics demo explores how NLP and GenAI-style workflows can be used to analyze political speech text. The broader project may include richer notebook steps, visualizations, model-based analysis, or larger data dependencies.

This quickstart is intentionally minimal. It is meant for a recruiter, reviewer, or collaborator who wants to confirm the demo structure and run a small CPU-only text analysis.

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
    print("No .txt or .md files found. Open the notebook for the full demo workflow.")
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

This confirms that the asset path exists and that basic text analysis can run with only the Python standard library.

Notebook path

To explore the intended workflow, open:

notebooks/sotu-speech-analytics/00_quickstart.ipynb

Depending on the notebook cells you run, the full workflow may require additional packages, larger datasets, API keys, or model downloads. Treat this document as a lightweight smoke test, not a guarantee that every notebook cell is CPU-only.

Notes for reviewers

This demo is intended to show:

practical NLP workflow design
exploratory text analysis
reproducible notebook structure
separation between assets, notebooks, and reusable source code

For a quick portfolio review, start with the notebook and this smoke test before running heavier model-based steps.

