# 🧠 GenAI Demos Portfolio

This repository contains a collection of demos showcasing **Generative AI techniques**.  
The notebooks are built with the latest Python libraries, support multiple GPU providers, and include references and explanations where relevant.  

👉 The goal: demonstrate practical implementations of GenAI concepts — from **image generation** to **multi-modal AI** — in a way that is both educational and extensible.  

---

## 📂 Contents & Topics

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
