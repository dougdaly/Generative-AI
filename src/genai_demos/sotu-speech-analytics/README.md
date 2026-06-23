# SOTU Speech Analytics (LLM-assisted)

Goal: instrument speeches (structure, rhetorical moves, framing) and compare 2012 vs 2020 vs 2024 SOTU.

## Data
Paste transcripts into:
- data/raw/2012.txt
- data/raw/2020.txt
- data/raw/2024.txt

Sources (Miller Center):
- 2012: <link>
- 2020: <link>
- 2024: <link>

## Quickstart
1) Create env + install deps
2) Run pipeline stages:
- sotu clean --config configs/v1.yaml
- sotu chunk --config configs/v1.yaml
- sotu topics --config configs/v1.yaml
- sotu metrics --config configs/v1.yaml

## Outputs
- data/clean/*.json
- data/chunks/*.jsonl
- data/derived/topics/*
- reports/figures/*

