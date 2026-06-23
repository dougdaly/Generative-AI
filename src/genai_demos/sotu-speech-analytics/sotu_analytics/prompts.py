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

Step 1: Choose exactly one DEVICE based on the speaker's main intent:
policy_ask, credit_claim, attack, exemplar, values, threat

Step 2: Choose exactly one TARGET:
the_public, institution, special_guests, domestic_opponents, foreign_adversaries, allies, unspecified

Step 3: Choose exactly one TONE (how it feels overall):
neutral, unifying, adversarial, upbeat, grave, urgent

DEVICE definitions and tie-break rules:
- policy_ask: proposes or asks for action/legislation/funding ("pass", "fund", "I propose", "my plan", "send me a bill", "get a bill to my desk").
  Tie-break: if there is a concrete ask, choose policy_ask even if values are mentioned.
- credit_claim: touts accomplishments/results or claims credit ("we achieved", "jobs are booming", "we cut", "I signed", statistics presented as achievements).
- attack: criticizes/blames opponents or contrasts with them ("they voted against", "the other side", "Democrats/Republicans"), WITHOUT needing to be insulting.
- exemplar: uses a named person/group story or honors someone as a persuasive example (special guests, victims, heroes, service members, "is here tonight", "in the gallery", "please stand").
  Tie-break: if the chunk centers on a person/story/tribute, choose exemplar unless it is overwhelmingly a legislative ask.
- values: moral/civic framing without a concrete ask (freedom, democracy, rights, dignity, fairness, who we are).
- threat: emphasizes danger/crisis/adversary/risk (war, terrorism, invasion, enemies, catastrophe, urgent security risks).
  Tie-break: if the chunk is primarily about danger/risk, choose threat even if it includes a call for unity.

TARGET guidance:
- institution: addressing Congress/the chamber ("members of Congress", "I ask Congress", "send me a bill").
- special_guests: addressing named guests or their families directly ("Megan, please stand", "thank you for being here").
- domestic_opponents: criticizing political opponents ("Democrats/Republicans", "the other side").
- foreign_adversaries: targeting foreign enemies (named leaders/regimes/terrorists).
- allies: praising/aligning with partners (NATO, allies, friendly nations).
- the_public: addressing Americans broadly ("the American people", "families", "workers").

Set uses_guest_example to true/false:
- true if a named individual is used as an example (guest story, victim/hero anecdote), even if the target is the_public or institution.

Evidence rules:
- evidence.device should quote the phrase that signals the device (ask/credit/blame/story/danger/values).
- evidence.target should quote the words that identify who is addressed (name/group/country).
- evidence.tone should quote a short phrase that conveys the tone.

Evidence must be valid JSON strings:
- Do NOT include double quote characters (") inside evidence fields.
- If the source text contains quotes, paraphrase the phrase without quotes.

Return JSON only (no prose):
{{
  "device": "...",
  "target": "...",
  "tone": "...",
  "uses_guest_example": true/false,
  "confidence": "low|med|high",
  "evidence": {{
    "device": "verbatim phrase (5-12 words)",
    "target": "verbatim phrase (5-12 words)",
    "tone": "verbatim phrase (5-12 words)"
  }}
}}

Chunk:
{chunk_text}
"""

