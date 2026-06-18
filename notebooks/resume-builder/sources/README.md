# Resume Generation Framework

## Objective

Generate market-aligned resumes from a structured career knowledge base while maintaining traceability between career evidence, inferred capabilities, and final resume claims.

---

## Phase 1: Master Resume

### Inputs

* Existing resumes
* LinkedIn profile
* Career notes
* Project summaries
* Awards, patents, certifications

### Outputs

* Master Resume.docx

### Status

Complete

### Key Decisions

* Separate resume content from archive content.
* Preserve accomplishments without concern for length.
* Capture career stories and supporting evidence for future use.

---

## Phase 2: Canonical Resume

### Inputs

* Master Resume.docx
* Canonical Resume Schema.md

### Outputs

* canonical_master_resume.json
* renderer.py
* standard.yaml
* canonical_master_resume.docx
* canonical_master_resume.pdf

### Status

Complete

### Key Decisions

* Content and presentation are separated.
* Schema uses a small number of reusable content types.
* Subsections became the primary reusable child-record structure.
* Renderers consume semantic content only.

### Validation

Master Resume
→ Canonical JSON
→ DOCX/PDF

Successful.

---

## Phase 3: Job Archetype Discovery

### Inputs

* archetype_hypothesis.json
* jd_search_contract.json
* seed_job_descriptions.json

### Outputs

* normalized_jds.json
* jd_signal_extractions.json
* canonical_market_signals.json
* target_archetype.json

### Status

In Progress

### Objective

Identify the capabilities, problem spaces, technologies, seniority signals, and business outcomes most valued by the target market.

### Key Principle

The archetype hypothesis guides job discovery but does not determine the final archetype.
