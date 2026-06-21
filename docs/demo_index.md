# Demo Index

This index highlights the most useful public review paths in the repository. Status notes are conservative: they identify what is present and where to start, but they do not guarantee that every notebook cell is CPU-only or free of external dependencies.

## Featured demo

### SOTU Speech Analytics

- Overview notebook: `notebooks/sotu-speech-analytics/00_sotu_speech_analytics_overview.ipynb`
- Quickstart: `docs/sotu_quickstart.md`
- Reusable source code: `src/demos/sotu-speech-analytics`
- Assets and generated outputs: `assets/sotu-speech-analytics`
- Status: public review path is present; heavier topic modeling, rhetoric analysis, embedding, and LLM-assisted steps may require additional dependencies, API access, or more compute than a CPU-only environment.

This is the best starting point for reviewers because it has a documented notebook entry point, reusable source code, and checked-in supporting artifacts.

## Notebook demos

- `notebooks/Stable_Diffusion.ipynb` - text-to-image diffusion workflow; likely requires model downloads and appropriate compute.
- `notebooks/Stability_API_Demo.ipynb` - image editing through the Stability AI API; requires API credentials.
- `notebooks/Building_a_Multimodal_RAG.ipynb` - multimodal retrieval-augmented generation demo.
- `notebooks/CLIP-from-ground-up.ipynb` - CLIP training walkthrough using image-caption data.
- `notebooks/a2a_agent_olympics.ipynb` - A2A agent-selection demo.
- `notebooks/langGraph-multi-agent-workflow.ipynb` - LangGraph multi-agent workflow.
- `notebooks/mtg-card-generator.ipynb` - multi-agent card-generation workflow.
- `notebooks/VAE_Example.ipynb` - variational autoencoder comparison.

## Reviewer notes

- Start with `README.md` for repository orientation.
- Use the SOTU quickstart for a lightweight CPU-only smoke test.
- Treat model training, hosted API calls, and large notebook runs as optional review steps unless a notebook states otherwise.
- Some demos are exploratory notebooks and may need environment-specific setup before they run end to end.
