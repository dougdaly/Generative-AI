# Generative AI Projects and Lessons

This repository is a public portfolio of Generative AI projects, teaching examples, and exploratory notebooks by Douglas Daly.

The work here reflects two related goals:

1. **Build practical AI systems** that connect LLMs, retrieval, agents, structured outputs, evaluation, observability, and human review into useful workflows.
2. **Teach modern AI concepts clearly** through small, reproducible lessons that explain how the patterns work, where they help, and where they break.

My focus is practical AI architecture: systems that are understandable, traceable, testable, and useful beyond the first demo.

## Start here

* Project index: `docs/project_index.md`
* Lesson index: `docs/lesson_index.md`
* Featured project: `projects/resume_builder/`
* Featured lesson: `lessons/a2a/`

Some examples require API keys, external datasets, larger model downloads, GPU acceleration, or additional setup. Check the relevant project or lesson README before running a full workflow.

## Repository structure

```text
projects/   End-to-end AI projects and portfolio systems
lessons/    Concept-focused teaching examples and walkthroughs
notebooks/  Jupyter notebooks for exploration, instruction, and prototypes
src/        Reusable Python package code shared across projects and lessons
docs/       Project indexes, lesson indexes, notes, and quickstarts
assets/     Small supporting assets used by examples
```

## Projects

The `projects/` folder contains larger AI systems organized around practical workflows or product-style artifacts. These are meant to show architecture judgment, implementation tradeoffs, and end-to-end design.

Examples include:

* **AI-Assisted Resume Generation System**
  Evidence-driven targeted resume generation using canonical JSON, market-derived role signals, structured LLM workflows, human review checkpoints, versioned artifacts, and DOCX/PDF rendering controls.

* **GraphRAG and Coverage Assistant**
  Traceable retrieval and structured decision support over connected evidence, entities, clauses, and reasoning paths.

* **Archival Restore**
  AI-assisted restoration and organization workflows for messy real-world media and metadata tasks.

A folder belongs in `projects/` when the primary goal is to build or simulate a useful AI-enabled workflow.

## Lessons

The `lessons/` folder contains smaller, concept-first examples designed for teaching and experimentation. These examples are intentionally narrower than the projects and are meant to be easy to run, inspect, and adapt.

Lesson topics include:

* Agent-to-agent coordination
* Model Context Protocol concepts
* Tool calling and structured outputs
* Retrieval-augmented generation
* Multi-agent orchestration
* Multimodal AI workflows
* Evaluation and regression detection
* Diffusion, CLIP, VAEs, GANs, and representation learning

A folder belongs in `lessons/` when the primary goal is to explain a concept, framework, protocol, or implementation pattern.

## Featured project: AI-Assisted Resume Generation System

The resume builder is an evidence-driven pipeline for creating targeted resume variants from a structured source resume.

It separates:

* Source evidence
* Canonical resume data
* Market-derived role signals
* Evidence-to-signal mapping
* Content selection
* Human review
* DOCX/PDF rendering

The goal is not to automate away judgment. The goal is to make the resume generation process more traceable, reviewable, and repeatable.

## Featured lesson: Agent-to-Agent Coordination

The A2A lessons introduce agent-to-agent coordination patterns through small, inspectable examples.

The goal is to show how specialized agents can expose capabilities, how a coordinating agent can route work, and how the system can log decisions and outputs for review.

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

Open the notebooks in Jupyter or VS Code. Use the project and lesson indexes to choose a starting point.

## Repository notes

* Keep examples reproducible where practical.
* Include sample outputs when they help reviewers understand the workflow.
* Do not commit large model checkpoints, private data, secrets, or licensed datasets.
* Use `projects/` for end-to-end systems and `lessons/` for concept-focused teaching examples.
* This repository is curated as a public portfolio and teaching resource.

## License

MIT. See the `LICENSE` file.

