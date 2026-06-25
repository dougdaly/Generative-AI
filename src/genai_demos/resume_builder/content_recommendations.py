from __future__ import annotations

import json
from typing import Any

from .capabilities import call_json_model


ADDITION_RECOMMENDATION_SCHEMA: dict[str, Any] = {
    "revision_request_summary": "...",
    "overall_recommendation": "...",
    "ranked_additions": [
        {
            "priority": 1,
            "action_type": "add_role_bullet | add_selected_project | none",
            "section_id": "EXPERIENCE | PROJECTS",
            "target": "human-readable role, subsection, or project name",
            "target_locator": {
                "section_id": "EXPERIENCE | PROJECTS",
                "organization": "organization name or null",
                "role": "role title or null",
                "label": "client subsection label, project label, or null",
            },
            "project_entry": {
                "label": "Project Name | Source | Year",
                "type": "bullet",
                "content": [
                    "Project bullet 1",
                    "Project bullet 2",
                ],
            },
            "source_evidence": [
                {
                    "evidence_id": "string or null",
                    "source_artifact": "canonical_resume | candidate_evidence | selected_evidence",
                    "source_location": "role/project/section name",
                    "evidence_statement": "specific supporting statement from the source",
                    "supported_scope": "narrowest accurate scope supported by the evidence",
                }
            ],
            "proposed_content": "...",
            "evidence_support": "direct | inferred | weak | unsupported",
            "target_relevance": "primary | secondary | weak",
            "target_signals_strengthened": ["..."],
            "why_this_adds_signal": "...",
            "why_not_another_option": "...",
            "redundancy_risk": "low | medium | high",
            "estimated_space_cost": "low | medium | high",
            "confidence": "low | medium | high",
        }
    ],
}


def get_target_profile(resume_positioning: dict[str, Any]) -> dict[str, Any]:
    """Extract the target profile fields needed for content recommendation."""
    target_title = resume_positioning.get("target_title")
    if not target_title:
        raise ValueError("resume_positioning is missing target_title")

    target_signals = resume_positioning.get("core_expertise")
    if not target_signals:
        raise ValueError("resume_positioning is missing core_expertise")

    summary = resume_positioning.get("summary", {})
    target_summary = summary.get("text") if isinstance(summary, dict) else None
    if not target_summary:
        raise ValueError("resume_positioning is missing summary.text")

    return {
        "target_title": target_title,
        "target_signals": target_signals,
        "target_summary": target_summary,
    }


def _json_for_prompt(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def build_addition_ranking_prompt(
    *,
    target_title: str,
    target_summary: str,
    target_signals: list[Any],
    human_revision_request: str,
    target_resume_content: dict[str, Any],
    canonical_resume: dict[str, Any],
    candidate_evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
    selected_evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
) -> str:
    """Build the prompt used to rank possible content additions.

    This prompt recommends additions only. It does not remove, rewrite, order,
    format, or render resume content.
    """
    candidate_evidence_text = (
        _json_for_prompt(candidate_evidence)
        if candidate_evidence is not None
        else "No separate candidate_evidence artifact was provided."
    )
    selected_evidence_text = (
        _json_for_prompt(selected_evidence)
        if selected_evidence is not None
        else "No separate selected_evidence artifact was provided."
    )
    output_schema_text = _json_for_prompt(ADDITION_RECOMMENDATION_SCHEMA)

    return f"""
You are reviewing a targeted resume content artifact.

Target title:
{target_title}

Target positioning summary:
{target_summary}

Target signals to strengthen:
{_json_for_prompt(target_signals)}

Human revision request:
{human_revision_request}

Current target resume content:
{_json_for_prompt(target_resume_content)}

Canonical resume:
{_json_for_prompt(canonical_resume)}

Candidate evidence:
{candidate_evidence_text}

Selected evidence:
{selected_evidence_text}

Task:
Identify and rank possible content additions.

A content addition may be:
1. an additional bullet under an existing professional experience role
2. an additional selected project
3. no addition, if nothing adds meaningful signal

Rules:
- Rank additions by marginal value for the target title and target signals.
- Prefer additions that strengthen underrepresented target signals.
- Prefer concrete professional delivery evidence over selected projects when both support the same signal.
- Prefer selected projects when they demonstrate a capability not already visible in professional experience.
- Penalize additions that repeat current target resume content.
- Penalize vague, generic, or low-evidence additions.
- Do not make layout, spacing, section order, or display heading decisions.
- Do not recommend omissions in this step.
- Do not invent facts not supported by the canonical resume, candidate evidence, or selected evidence.
- Every recommendation that can be applied must include a deterministic target_locator.
- For add_role_bullet, project_entry must be null.
- For add_selected_project, project_entry must be a complete PROJECTS-compatible subsection object.
- For action_type none, target_locator and project_entry may be null.
- target is for human review only; target_locator is for applying changes.

Recommendation count rules:
- Return 5 to 10 ranked additions when supported evidence is available.
- Do not stop after the first strong recommendation.
- If fewer than 5 supported additions are available, return all supported additions and explain why there are fewer.
- Each ranked addition must have a unique integer priority starting at 1.

Additional content allocation rules:
- Consider current bullet count, role duration, and target relevance when ranking additions.
- Downweight additions that would give a short role or client engagement more than 2 total bullets, unless the added bullet covers a primary target signal not covered elsewhere.
- When two additions have similar target relevance and evidence strength, prefer the one that improves resume balance across high-relevance roles.
- Do not treat role duration as a hard cap. A short but highly relevant role may receive more bullets if the additional evidence is unusually strong and non-redundant.

Evidence rules:
- For every proposed addition, first identify the supporting evidence.
- Return the evidence statement separately from the proposed resume bullet.
- Use the narrowest accurate scope supported by the evidence.
- The proposed content must not broaden scope, impact, ownership, scale, or technical claims beyond the evidence statement.
- If support is weak or unsupported, mark evidence_support accordingly and lower confidence.
- When multiple additions have similar value, prefer additions from underrepresented high-relevance roles or projects rather than adding several bullets to the same role.
- Do not use general expertise, plausibility, or synthesis as evidence for a new role bullet or selected project.
- Rank by target relevance first, then evidence strength, then space cost.
- A directly supported bullet with weak target relevance should rank below a directly supported bullet with primary target relevance.
- Prefer additions tied to primary target signals over secondary signals unless the primary signal is already fully represented.
- Use role_context and summary_context to understand scale, business importance, operating environment, and why the evidence mattered.
- Do not treat role_context or summary_context as standalone accomplishments.
- Evidence_text remains the accomplishment being scored.
- Context may strengthen interpretation when it clarifies the scope or significance of evidence_text.
- Preserve source_context literally; it may describe client, employer, institution, or source relationship.

Return JSON only using this structure:
{output_schema_text}
"""


def rank_content_additions(
    *,
    target_title: str | None = None,
    target_summary: str | None = None,
    target_signals: list[Any] | None = None,
    target_profile: dict[str, Any] | None = None,
    human_revision_request: str,
    target_resume_content: dict[str, Any] | None = None,
    current_resume_content: dict[str, Any] | None = None,
    canonical_resume: dict[str, Any],
    candidate_evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
    selected_evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
    model: str,
) -> dict[str, Any]:
    """Generate ranked recommendations for adding resume content.

    Accepts either explicit target_title/summary/signals or a target_profile dict
    returned by get_target_profile().

    Accepts target_resume_content or current_resume_content as aliases.
    """
    resume_content = target_resume_content or current_resume_content
    if resume_content is None:
        raise ValueError("rank_content_additions requires target_resume_content or current_resume_content")

    if target_profile is not None:
        target_title = target_profile.get("target_title")
        target_summary = target_profile.get("target_summary")
        target_signals = target_profile.get("target_signals")

    if not target_title:
        raise ValueError("rank_content_additions is missing target_title")
    if not target_summary:
        raise ValueError("rank_content_additions is missing target_summary")
    if not target_signals:
        raise ValueError("rank_content_additions is missing target_signals")

    prompt = build_addition_ranking_prompt(
        target_title=target_title,
        target_summary=target_summary,
        target_signals=target_signals,
        human_revision_request=human_revision_request,
        target_resume_content=resume_content,
        canonical_resume=canonical_resume,
        candidate_evidence=candidate_evidence,
        selected_evidence=selected_evidence,
    )

    result = call_json_model(prompt, model)

    if not isinstance(result, dict):
        raise TypeError(
            f"Expected call_json_model() to return dict, got {type(result).__name__}"
        )

    return result
