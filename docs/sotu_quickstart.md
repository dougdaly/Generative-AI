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
