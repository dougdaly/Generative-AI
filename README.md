# GenAI Demos Portfolio

This repository is a public portfolio of Generative AI demos, experiments, and instructional notebooks by Douglas Daly. It is intended for reviewers and collaborators who want to inspect practical examples of diffusion, CLIP, RAG, multi-agent orchestration, speech analytics, VAEs, GANs, and related workflows.

## Start here

- Demo index: `docs/demo_index.md`
- Featured demo quickstart: `docs/sotu_quickstart.md`
- Featured demo notebook: `notebooks/sotu-speech-analytics/00_sotu_speech_analytics_overview.ipynb`

Some notebooks require API keys, large model downloads, GPU acceleration, or external datasets. Check the relevant notebook or quickstart before running a full workflow.

## Featured demo: SOTU Speech Analytics

The SOTU Speech Analytics demo analyzes State of the Union speech text and separates the public review path from heavier model-backed steps.

- Overview notebook: `notebooks/sotu-speech-analytics/00_sotu_speech_analytics_overview.ipynb`
- Reusable source code: `src/demos/sotu-speech-analytics`
- Supporting assets and generated outputs: `assets/sotu-speech-analytics`
- Reviewer quickstart: `docs/sotu_quickstart.md`

For a quick review, start with the overview notebook and quickstart. The reusable source tree contains preprocessing, topic modeling, rhetoric analysis, and reporting scripts; some of those stages may require additional dependencies, API access, or more compute than a CPU-only environment.

## Demo areas

- Tool and agent sharing: A2A, MCP, FastAPI
- Multi-agent workflows: LangGraph and LangChain examples
- Retrieval-augmented generation: text and multimodal RAG examples
- Multimodal orchestration: text, image, and research workflows
- Image generation and editing: diffusion, Stability AI API, GANs
- Representation learning: CLIP, VAEs, score-based models
- Speech analytics: SOTU text analysis with reusable source and generated artifacts

## Local setup

```bash
git clone https://github.com/dougdaly/Generative-AI.git
cd Generative-AI
conda env create -f environment_min.yml
conda activate genai
```

Alternatively, use a Python virtual environment and `requirements.txt`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Open the notebooks in Jupyter or VS Code. Use `docs/demo_index.md` to choose a starting point.

## Repository notes

- Sample outputs and generated artifacts are included where useful for review.
- Do not commit large model checkpoints, private data, secrets, or licensed datasets.
- This repository is curated as a public portfolio; open an issue or pull request for proposed additions.

## License

MIT. See the `LICENSE` file.
