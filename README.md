# 🧠 GenAI Demos Portfolio

This repository contains a collection of demos showcasing **Generative AI techniques**.  
The notebooks are built with the latest Python libraries, support multiple GPU providers, and include references and explanations where relevant.  

👉 The goal: demonstrate practical implementations of GenAI concepts — such as **image generation**, **RAG methodologies**, **agent orchestration with LangGraph, A2A and MCP**, and **multi-modal AI** — in a way that is both educational and extensible.  

---

## 📂 Contents & Topics
### 🔹 Tool & Agent sharing across team**s (A2A, MCP, FastAPI)
- **a2a_olympics.ipynb** → leverages A2A protocol to select optimal agents for selected tasks. Compares results against contract with a general-purpose agent.
- **archival_restore.ipynb** → applies model context protocol (MCP) to develop an image enhancement approach optimal for OCR exploitation on a 130 year-old diary.
### 🔹 Multi-Agent Workflows (LangGraph / LangChain)
- **mtg-card-generator.ipynb** → shows the benefits of using multiple agents for a complex task: building new creature cards for a popular trading card game (Magic: The Gathering)
- **langGraph-multi-agent-workflow.ipynb** → combines a search agent + image generation agent (OpenAI) to generate a grid of famous athletes by country.  
- **langGraph-alphabet.ipynb** → creates an AI-powered children’s alphabet poster with words + images.  

### 🔹 GANs (Generative Adversarial Networks)
- **dcgan_faces_tutorial.ipynb** → trains a GAN on a celebrity dataset, demonstrating generator vs discriminator competition and pitfalls of the approach.
- **GAN_for_images_MLP_vs_CNN** → Proves "NN architecture matters". Compares the results of building a GAN with a dense NN vs a CNN. The dense NN fails as it does not have a sense of space.

### 🔹 CLIP (Contrastive Language–Image Pretraining)
- **CLIP-from-ground-up.ipynb** → builds a CLIP model from scratch on Flickr dataset (images + captions).  
- **CLIP_tuning.ipynb** → fine-tunes a CLIP model for domain-specific tasks (example: aerial imagery).  

### 🔹 Retrieval-Augmented Generation (RAG)
- **Building_a_multimodal_RAG.ipynb** → queries both stored text and images with multimodal input.  

### 🔹 Speech Analytics
- **SOTU Speech Analytics** → public portfolio demo for analyzing State of the Union speech text. Start with `notebooks/sotu-speech-analytics/00_sotu_speech_analytics_overview.ipynb`; reusable code is under `src/demos/sotu-speech-analytics`, and supporting data, figures, tables, and writeups are under `assets/sotu-speech-analytics`. See `docs/sotu_quickstart.md` for a CPU-only smoke test and notes on heavier model steps.

### 🔹 Multimodal orchestration
- **Agentic-Multimodal.ipynb** → solves a common problem with creating images with text by combining an orchestrator agent, image generation through a CLIP model, and a research tool for factual data. Builds posters of leaders with names & time in office, maps of the world with country & capital with a picture of a nation's celebrity, and maps a great circle route between two places on the globe.
### 🔹 Diffusion Models
- **annotated_diffusion.ipynb** → step-by-step theory & math of progressive noise addition with MNIST fashion dataset.  
- **score_based_diffusion.ipynb** → implements score-based diffusion with ODE solver.  
- **Stable_Diffusion.ipynb** → uses HuggingFace diffusion models with CLIP text encoder for text-to-image generation.  

### 🔹 Stability.ai API
- **Stability_API_Demo.ipynb** → demonstrates masking, overlaying, background replacement, and other image-editing tasks via Stability.ai API.  

### 🔹 Variational Autoencoders (VAE)
- **VAE_Example.ipynb** → compares a standard autoencoder vs a variational autoencoder to explain the power of VAEs.  

---

## 🚀 Tech Stack
- **Python** (latest libraries)  
- **PyTorch / HuggingFace / LangChain / LangGraph**  
- **Diffusion, GANs, CLIP, RAG, VAEs**  
- **APIs**: Stability.ai, OpenAI  

---

## 📊 Results
Sample outputs are stored in the `results/` folder.  
> 🔎 These are not required to run the demos — they simply illustrate recent experiments.

---

## 🧩 How to Use
1. Clone the repo:
   ```bash
   git clone https://github.com/your-username/genai-demos.git
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
