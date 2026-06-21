# GenAI Demos — Public Portfolio

This repository is a public portfolio of Generative AI demos, experiments, and instructional notebooks by Douglas Daly. It is intended to showcase practical implementations of GenAI approaches (diffusion, CLIP, RAG, multi-agent orchestration, VAEs, GANs, and more) and to provide runnable demos for reviewers and collaborators.

Highlights
- Curated notebooks showing end-to-end demos and exploratory research
- Lightweight quickstarts to run selected demos locally
- Demo index and short status notes in docs/demo_index.md
- License: MIT (LICENSE file)

Quick start (local, minimal)
1. Clone:
   git clone https://github.com/dougdaly/Generative-AI.git
2. Create env:
   conda env create -f environment_min.yml
   conda activate genai
   or
   python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
3. Open Jupyter / VS Code and run notebooks/* (see docs/demo_index.md for recommended demos)
4. NOTE: Some demos require large models / API keys / datasets. Check notebook headers and docs before running.

Contributing
- This repo is curated as a public portfolio. For contributions, open an issue or PR describing additions.
- Do not commit large model checkpoints or sensitive data.

Docs
- docs/demo_index.md — top demos and status
- docs/sotu_quickstart.md — minimal quickstart for sotu-speech-analytics

License
- MIT (see LICENSE)

## Featured Demos

### agentic_multimodal
- What it demonstrates: agent orchestration for multimodal tasks (combining agents for image generation and factual retrieval). (Folder exists: no .ipynb files found.)
- Why it matters: shows patterns for coordinating multiple models/tools and handling multimodal inputs.
- Runnable now: Folder exists: no .ipynb files found.. Notebook files may require large model downloads and API keys; not guaranteed runnable out-of-the-box.

### sotu-speech-analytics
- What it demonstrates: pipeline components for State-of-the-Union speech analysis (cleaning, chunking, topic discovery, metrics, visualization). (Folder exists: no .ipynb files found.)
- Why it matters: example of text preprocessing and analytic pipelines applied to political speech.
- Runnable now: Folder exists: no .ipynb files found.. Many files appear to be placeholders; requires populated notebooks and transcripts to run.

### resume-builder
- What it demonstrates: tools and notebooks for reviewing and extracting evidence for resumes (e.g., evidence review notebooks). (Folder exists: no .ipynb files found.)
- Why it matters: illustrates information extraction and structured review workflows relevant to applicant evaluation and resume automation.
- Runnable now: Folder exists: no .ipynb files found.. May require datasets and environment setup; run after reviewing notebook headers for requirements.
