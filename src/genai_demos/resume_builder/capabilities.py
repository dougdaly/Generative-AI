import json
from copy import deepcopy
import re

def extract_json_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    return text

def call_json_model(prompt, model, VERBOSE=False):
    response = model.invoke(prompt)

    text = (
        response.content
        if hasattr(response, "content")
        else str(response)
    )
    if VERBOSE:
        print("Response type:", type(response))
        print("Text type:", type(text))
        print("Text length:", len(text) if isinstance(text, str) else "not str")
        print("Text preview:")
        print(str(text)[:1000])

    text = extract_json_text(str(text))

    return json.loads(text)


def build_capability_review(
    bullet_review,
    target_resume_strategy,
    model,
    min_include_score=4,
):
    selected = [
        row for row in bullet_review
        if row.get("include_score", 0) >= min_include_score
    ]

    prompt = f"""
Extract demonstrated capabilities from resume bullet evidence.

Use ONLY the provided evidence. Do not invent capabilities.

Target strategy:
{json.dumps(target_resume_strategy, indent=2)}

Bullet evidence:
{json.dumps(selected, indent=2)}

Return valid JSON only:

{{
  "capability_review": [
    {{
      "bullet_id": "...",
      "source_role": "...",
      "evidence_theme": "...",
      "bullet": "...",
      "capabilities": [
        {{
          "name": "...",
          "evidence_strength": 1-5,
          "market_relevance": 1-5,
          "specificity": 1-5,
          "notes": "Brief reason this capability is supported."
        }}
      ]
    }}
  ]
}}
"""
    return call_json_model(prompt, model)

def build_core_expertise_candidates(
    capability_review,
    target_resume_strategy,
    model,
    max_categories=5,
    max_items_per_category=7,
):
    prompt = f"""
Create resume-facing Core Expertise categories from demonstrated capabilities.

Do not make generic weak categories like:
- Programming
- Cloud & Platforms
unless the category has strong evidence and strategic value.

Prefer capability-oriented categories such as:
- Applied AI Systems
- AI Governance & Production Readiness
- Data & Decision Systems
- Operational Intelligence
- Enterprise AI Architecture

Target strategy:
{json.dumps(target_resume_strategy, indent=2)}

Capability review:
{json.dumps(capability_review, indent=2)}

Return valid JSON only:

{{
  "core_expertise_candidates": [
    {{
      "label": "...",
      "items": ["...", "..."],
      "evidence_basis": ["...", "..."],
      "rationale": "...",
      "category_strength": 1-5
    }}
  ]
}}

Constraints:
- Use at most {max_categories} categories.
- Use at most {max_items_per_category} items per category.
- Items should be short resume phrases.
- Prefer evidence-backed capabilities over standalone tool names.
"""
    return call_json_model(prompt, model)


def core_expertise_to_section(core_expertise_candidates):
    return {
        "heading": "Core Expertise",
        "type": "subsections",
        "content": [
            {
                "label": category["label"],
                "type": "inline_list",
                "content": category["items"],
            }
            for category in core_expertise_candidates["core_expertise_candidates"]
            if category.get("category_strength", 0) >= 3
        ],
    }


def replace_section(resume, new_section):
    resume = deepcopy(resume)
    heading = new_section["heading"]

    for i, section in enumerate(resume["sections"]):
        if section.get("heading") == heading:
            resume["sections"][i] = new_section
            return resume

    resume["sections"].append(new_section)
    return resume