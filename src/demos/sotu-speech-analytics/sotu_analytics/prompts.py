from __future__ import annotations
from typing import List, Dict

def build_topic_label_prompt(year, topic_id, ngram_terms, excerpts):
    terms_block = "\n".join([f"- {t}" for t in ngram_terms[:12]])
    ex_block = "\n".join([f"{i+1}) {e}" for i, e in enumerate(excerpts)])
    return f"""You are labeling a topic cluster from a State of the Union speech ({year}).

Return JSON with keys:
- label: 1-4 words, neutral policy/theme noun phrase
- confidence: low|med|high
- keywords: up to 6
- rationale: 1 sentence grounded in evidence

Rules:
- Ignore personal names and applause/gallery scaffolding.
- Prefer conventional topic names (e.g., "border security", "drug prices", "neonatal care").
- If the cluster is mostly a personal story, label the underlying policy/theme, not the person.

Top n-gram candidates:
{terms_block}

Representative excerpts:
{ex_block}

Return JSON only.
"""


def build_disambiguate_prompt(
    label: str,
    topics: List[Dict],  # each has topic_id, excerpts, ngrams
) -> str:
    blocks = []
    for t in topics:
        ex = "\n".join([f"- {e}" for e in t["excerpts"][:4]])
        ng = ", ".join(t["ngram_terms"][:10])
        blocks.append(f"Topic {t['topic_id']} ngrams: {ng}\nExcerpts:\n{ex}\n")
    joined = "\n---\n".join(blocks)

    return f"""Two or more clusters were labeled "{label}". Make them distinct.

    You have all necessary information below. Do not ask questions.

    Task:
    - Provide a refined label for each topic as: "{label}: <2-4 word qualifier>"
    - Do NOT repeat "{label}" inside the qualifier.
    - Qualifier must be grounded in the excerpts/ngrams.
    - Keep labels neutral and policy/theme focused.

    Return JSON mapping topic_id -> refined_label.
    Example:
    {{"3": "{label}: jobs and wages", "7": "{label}: trade and industry"}}

    {joined}

    Return JSON only. No prose.
    """


def build_rhetoric_prompt(year: int, chunk_text: str) -> str:
    return f"""Classify the rhetoric in this State of the Union speech chunk ({year}).

Choose exactly one tone:
neutral, unifying, adversarial, upbeat, grave, urgent, defiant, conciliatory

Choose exactly one device:
policy_proposal, scoreboard, attack_contrast, ridicule, tribute, anecdote, values_frame, warning_threat, call_to_action

Choose exactly one target:
the_public, institution, special_guests, domestic_opponents, foreign_adversaries, allies, unspecified

Device guidance (use these tie-break rules):
- anecdote: centers on a named individual/special guest ("is here tonight", "in the gallery", personal story as hook). If present, choose anecdote unless the chunk is overwhelmingly policy text.
- tribute: honors/thanks a person or group for sacrifice/service (heroes, victims, military families). Often overlaps with anecdote; if the intent is honoring, choose tribute.
- scoreboard: claims credit or touts results ("we achieved", "jobs are booming", "I signed", statistics as achievements).
- policy_proposal: asks for or proposes action ("pass", "fund", "I propose", "my plan", "get a bill to my desk").
- values_frame: moral/civic framing (freedom, democracy, rights, dignity, fairness) without a specific ask.
- warning_threat: emphasizes danger/crisis/adversary/risk (security threats, crises, enemies).
- attack_contrast: criticizes/blames opponents or contrasts with them, without explicit derision.
- ridicule: explicit derision/shaming/name-calling or humiliation setups aimed at a target (stronger than attack_contrast).
- call_to_action: direct imperative to act/stand/support now.

If unsure between two devices, choose the one that best matches the main purpose of the chunk.

Target guidance:
- institution: addressing Congress/the chamber ("members of Congress", "I ask Congress", "send me a bill").
- special_guests: addressing named guests or their families.
- domestic_opponents: criticizing "Democrats/Republicans/the other side" or political opponents.
- foreign_adversaries: targeting foreign enemies (Putin, terrorists, hostile regimes).
- the_public: addressing Americans broadly ("the American people", "families", "workers").

Also set uses_guest_example to true/false (true if a named person is used as an example, even if target is different).

Return JSON only:
{{
  "tone": "...",
  "device": "...",
  "target": "...",
  "uses_guest_example": true/false,
  "confidence": "low|med|high",
  "evidence": {{
    "tone": "verbatim phrase (5-12 words)",
    "device": "verbatim phrase (5-12 words)",
    "target": "verbatim phrase indicating who (e.g., name, group, country)"
  }}
}}

Chunk:
{chunk_text}
"""

