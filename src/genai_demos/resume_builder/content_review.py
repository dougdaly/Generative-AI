from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .helpers import load_json, load_text, save_text


CONTENT_FILE_PATTERN = re.compile(r"target_resume_content_v(\d+)\.json$")
ALLOWED_EVIDENCE_SUPPORT_FOR_APPLY = {"direct", "inferred"}


# -----------------------------------------------------------------------------
# Version loading
# -----------------------------------------------------------------------------


def find_latest_content_version(artifact_dir: str | Path) -> str:
    """Return the latest target resume content version, e.g. 'v3'."""
    artifact_dir = Path(artifact_dir)
    versions: list[int] = []

    for path in artifact_dir.glob("target_resume_content_v*.json"):
        match = CONTENT_FILE_PATTERN.match(path.name)
        if match:
            versions.append(int(match.group(1)))

    if not versions:
        raise FileNotFoundError(
            f"No target_resume_content_v*.json files found in {artifact_dir}"
        )

    return f"v{max(versions)}"


def load_target_content(
    artifact_dir: str | Path,
    version: str = "latest",
) -> tuple[dict[str, Any], str]:
    """Load a target_resume_content_vN.json artifact."""
    artifact_dir = Path(artifact_dir)
    resolved_version = find_latest_content_version(artifact_dir) if version == "latest" else version
    path = artifact_dir / f"target_resume_content_{resolved_version}.json"

    if not path.exists():
        raise FileNotFoundError(f"Target resume content file not found: {path}")

    return load_json(path), resolved_version


def next_content_version(version: str) -> str:
    """Return the next version label, e.g. v2 -> v3."""
    match = re.fullmatch(r"v(\d+)", str(version).strip())
    if not match:
        raise ValueError(f"Expected version like 'v2', got {version!r}")
    return f"v{int(match.group(1)) + 1}"


# -----------------------------------------------------------------------------
# Human-readable display
# -----------------------------------------------------------------------------


def _clean_join(parts: list[Any], sep: str = " | ") -> str:
    return sep.join(str(part).strip() for part in parts if str(part or "").strip())


def display_subsection_block(block: dict[str, Any]) -> None:
    """Display a canonical subsection block."""
    label = block.get("label", "")
    context = block.get("context", "")
    dates = block.get("dates", "")
    block_type = block.get("type", "")
    content = block.get("content", [])

    heading = _clean_join([label, context, dates])
    if heading:
        print("\n" + heading)

    if block_type == "bullet":
        for item in content:
            print(f"- {item}")

    elif block_type == "paragraph":
        for item in content:
            print(item)

    elif block_type == "inline_list":
        if isinstance(content, list):
            print(", ".join(str(x) for x in content))
        else:
            print(content)

    else:
        if isinstance(content, list):
            for item in content:
                print(f"- {item}")
        elif content:
            print(content)


def display_target_resume_text(target_resume_content: dict[str, Any]) -> None:
    """Print target resume content in a readable plain-text form."""
    header = target_resume_content.get("header", {})

    print("=" * 100)
    print(header.get("name", ""))
    print("=" * 100)

    for section in target_resume_content.get("sections", []):
        print("\n" + "=" * 100)
        print(str(section.get("heading", "")).upper())
        print("=" * 100)

        section_type = section.get("type")

        if section_type == "paragraph":
            for paragraph in section.get("content", []):
                print(paragraph)

        elif section_type == "bullet":
            for bullet in section.get("content", []):
                print(f"- {bullet}")

        elif section_type == "inline_list":
            print(", ".join(str(x) for x in section.get("content", [])))

        elif section_type == "subsections":
            for block in section.get("content", []):
                if isinstance(block, dict):
                    display_subsection_block(block)
                else:
                    print(f"- {block}")

        elif section_type == "experience":
            for exp in section.get("content", []):
                print(
                    "\n"
                    + _clean_join(
                        [exp.get("role", ""), exp.get("organization", ""), exp.get("dates", "")]
                    )
                )

                for item in exp.get("content", []):
                    if isinstance(item, str):
                        print(f"- {item}")
                    elif isinstance(item, dict):
                        label = item.get("label", "")
                        context = item.get("context", "")
                        dates = item.get("dates", "")
                        heading = _clean_join([label, context, dates])
                        if heading:
                            print(f"\n{heading}")
                        for bullet in item.get("content", []):
                            print(f"- {bullet}")

        else:
            print(f"[Unsupported section type: {section_type}]")
            print(section.get("content", ""))


# -----------------------------------------------------------------------------
# Manual review text export/import
# -----------------------------------------------------------------------------


def _get_path(root: Any, path: list[Any]) -> Any:
    value = root
    for token in path:
        value = value[token]
    return value


def _set_path(root: Any, path: list[Any], value: Any) -> None:
    parent = _get_path(root, path[:-1])
    parent[path[-1]] = value


def _normalize_review_text(text: str, normalize_whitespace: bool = True) -> str:
    text = text.strip()
    if normalize_whitespace:
        text = re.sub(r"\s+", " ", text)
    return text


def _add_editable_block(
    blocks: list[dict[str, Any]],
    *,
    path: list[Any],
    text_type: str,
    source: str,
    text: str,
) -> None:
    if not isinstance(text, str):
        return

    if not text.strip():
        return

    blocks.append(
        {
            "block_id": f"T{len(blocks) + 1:04d}",
            "path_json": path,
            "type": text_type,
            "source": source,
            "text": text,
        }
    )


def _collect_content_strings(
    blocks: list[dict[str, Any]],
    *,
    content: Any,
    path: list[Any],
    text_type: str,
    source: str,
) -> None:
    if isinstance(content, list):
        for idx, item in enumerate(content):
            if isinstance(item, str):
                _add_editable_block(
                    blocks,
                    path=[*path, idx],
                    text_type=text_type,
                    source=source,
                    text=item,
                )


def collect_editable_text_blocks(
    target_resume_content: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    Collect editable resume prose/bullet strings.

    The collector intentionally skips labels, headings, dates, organizations, and roles.
    This final review pass is for wording of existing resume content, not structure edits.
    """
    blocks: list[dict[str, Any]] = []

    for section_idx, section in enumerate(target_resume_content.get("sections", [])):
        section_type = section.get("type")
        section_heading = section.get("heading") or section.get("section_id") or f"section {section_idx}"
        section_path = ["sections", section_idx]

        if section_type in {"paragraph", "bullet", "inline_list"}:
            _collect_content_strings(
                blocks,
                content=section.get("content", []),
                path=[*section_path, "content"],
                text_type=section_type,
                source=str(section_heading).upper(),
            )

        elif section_type == "subsections":
            for block_idx, block in enumerate(section.get("content", [])):
                if not isinstance(block, dict):
                    continue
                source = _clean_join(
                    [section_heading, block.get("label"), block.get("context"), block.get("dates")],
                    sep=" / ",
                )
                _collect_content_strings(
                    blocks,
                    content=block.get("content", []),
                    path=[*section_path, "content", block_idx, "content"],
                    text_type=f"subsection_{block.get('type', 'content')}",
                    source=source,
                )

        elif section_type == "experience":
            for exp_idx, exp in enumerate(section.get("content", [])):
                exp_source = _clean_join(
                    [exp.get("role"), exp.get("organization"), exp.get("dates")]
                )
                exp_path = [*section_path, "content", exp_idx]

                for item_idx, item in enumerate(exp.get("content", [])):
                    if isinstance(item, str):
                        _add_editable_block(
                            blocks,
                            path=[*exp_path, "content", item_idx],
                            text_type="experience_bullet",
                            source=exp_source,
                            text=item,
                        )
                    elif isinstance(item, dict):
                        subsection_source = _clean_join(
                            [
                                exp_source,
                                item.get("label"),
                                item.get("context"),
                                item.get("dates"),
                            ]
                        )
                        _collect_content_strings(
                            blocks,
                            content=item.get("content", []),
                            path=[*exp_path, "content", item_idx, "content"],
                            text_type="experience_bullet",
                            source=subsection_source,
                        )

    return blocks


def export_manual_review_text(
    *,
    target_resume_content: dict[str, Any],
    review_text_path: str | Path,
) -> list[dict[str, Any]]:
    """Export editable resume text blocks to a round-trippable plain text file."""
    blocks = collect_editable_text_blocks(target_resume_content)

    lines = [
        "# Target Resume Manual Review File",
        "#",
        "# Edit only the text after TEXT: inside each block.",
        "# Do not edit @@TEXT, PATH_JSON, TYPE, SOURCE, or @@END lines.",
        "# Do not add or delete blocks in this final wording pass.",
        "",
    ]

    for block in blocks:
        lines.extend(
            [
                f"@@TEXT {block['block_id']}",
                f"PATH_JSON: {json.dumps(block['path_json'], ensure_ascii=False)}",
                f"TYPE: {block['type']}",
                f"SOURCE: {block['source']}",
                "TEXT:",
                block["text"],
                "@@END",
                "",
            ]
        )

    save_text("\n".join(lines), review_text_path)
    return blocks


def _parse_manual_review_text(review_text: str) -> dict[str, dict[str, Any]]:
    lines = review_text.splitlines()
    blocks: dict[str, dict[str, Any]] = {}
    idx = 0

    while idx < len(lines):
        line = lines[idx].strip()

        if not line or line.startswith("#"):
            idx += 1
            continue

        match = re.fullmatch(r"@@TEXT\s+(T\d{4})", line)
        if not match:
            raise ValueError(f"Unexpected line outside block at line {idx + 1}: {lines[idx]!r}")

        block_id = match.group(1)
        if block_id in blocks:
            raise ValueError(f"Duplicate block_id in manual review file: {block_id}")

        try:
            path_line = lines[idx + 1]
            type_line = lines[idx + 2]
            source_line = lines[idx + 3]
            text_marker = lines[idx + 4]
        except IndexError as exc:
            raise ValueError(f"Incomplete block for {block_id}") from exc

        if not path_line.startswith("PATH_JSON: "):
            raise ValueError(f"{block_id}: expected PATH_JSON line")
        if not type_line.startswith("TYPE: "):
            raise ValueError(f"{block_id}: expected TYPE line")
        if not source_line.startswith("SOURCE: "):
            raise ValueError(f"{block_id}: expected SOURCE line")
        if text_marker.strip() != "TEXT:":
            raise ValueError(f"{block_id}: expected TEXT: marker")

        path_json = json.loads(path_line.split(": ", 1)[1])
        text_type = type_line.split(": ", 1)[1]
        source = source_line.split(": ", 1)[1]

        text_lines: list[str] = []
        idx += 5
        while idx < len(lines) and lines[idx].strip() != "@@END":
            text_lines.append(lines[idx])
            idx += 1

        if idx >= len(lines):
            raise ValueError(f"{block_id}: missing @@END")

        blocks[block_id] = {
            "block_id": block_id,
            "path_json": path_json,
            "type": text_type,
            "source": source,
            "text": "\n".join(text_lines),
        }

        idx += 1

    return blocks


def import_manual_review_text(
    *,
    base_resume_content: dict[str, Any],
    review_text_path: str | Path,
    normalize_whitespace: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Import edited manual review text back into the target resume content JSON."""
    base_blocks = collect_editable_text_blocks(base_resume_content)
    edited_blocks = _parse_manual_review_text(load_text(review_text_path))

    base_ids = {block["block_id"] for block in base_blocks}
    edited_ids = set(edited_blocks)

    missing = sorted(base_ids - edited_ids)
    extra = sorted(edited_ids - base_ids)

    if missing or extra:
        raise ValueError(
            "Manual review file block mismatch. "
            f"Missing blocks: {missing}. Extra blocks: {extra}."
        )

    updated = deepcopy(base_resume_content)
    changes: list[dict[str, Any]] = []
    unchanged_count = 0

    for base_block in base_blocks:
        block_id = base_block["block_id"]
        edited_block = edited_blocks[block_id]

        if edited_block["path_json"] != base_block["path_json"]:
            raise ValueError(f"{block_id}: PATH_JSON was changed. This is not allowed.")

        old_text = str(_get_path(base_resume_content, base_block["path_json"]))
        new_text = _normalize_review_text(
            edited_block["text"],
            normalize_whitespace=normalize_whitespace,
        )
        if not new_text:
            if base_block["type"] in {"experience_bullet", "project_bullet"}:
                _set_path(updated, base_block["path_json"], "")
                changes.append(
                    {
                        "block_id": block_id,
                        "path_json": base_block["path_json"],
                        "type": base_block["type"],
                        "source": base_block["source"],
                        "change_type": "blanked",
                        "before": old_text,
                        "after": "",
                    }
                )
                continue

            raise ValueError(f"{block_id}: edited text is empty.")

        if new_text == old_text:
            unchanged_count += 1
            continue

        _set_path(updated, base_block["path_json"], new_text)
        changes.append(
            {
                "block_id": block_id,
                "path_json": base_block["path_json"],
                "type": base_block["type"],
                "source": base_block["source"],
                "before": old_text,
                "after": new_text,
            }
        )

    edit_log = {
        "revision_type": "manual_wording_review",
        "review_text_path": str(review_text_path),
        "editable_block_count": len(base_blocks),
        "changed_count": len(changes),
        "unchanged_count": unchanged_count,
        "changes": changes,
    }

    return updated, edit_log


# -----------------------------------------------------------------------------
# Addition recommendation display and apply helpers
# -----------------------------------------------------------------------------


def normalize_section_id(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_priority(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid recommendation priority: {value!r}") from exc


def get_section_by_id(resume_content: dict[str, Any], section_id: str) -> dict[str, Any]:
    section_id = normalize_section_id(section_id)

    matches = [
        section
        for section in resume_content.get("sections", [])
        if normalize_section_id(section.get("section_id", "")) == section_id
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one section_id={section_id!r}, found {len(matches)}."
        )

    return matches[0]


def append_unique_bullet(bullets: list[str], bullet: str) -> str:
    bullet = str(bullet).strip()

    if not bullet:
        raise ValueError("Cannot add an empty bullet.")

    existing = {str(item).strip() for item in bullets}

    if bullet in existing:
        return "skipped_duplicate"

    bullets.append(bullet)
    return "added"


def find_experience_bullet_list(
    experience_section: dict[str, Any],
    target_locator: dict[str, Any],
) -> list[str]:
    organization = target_locator.get("organization")
    role = target_locator.get("role")
    label = target_locator.get("label")

    if not organization or not role:
        raise ValueError(
            "target_locator for add_role_bullet must include organization and role."
        )

    role_matches = [
        item
        for item in experience_section.get("content", [])
        if item.get("organization") == organization and item.get("role") == role
    ]

    if len(role_matches) != 1:
        raise ValueError(
            "Expected exactly one experience role match for "
            f"organization={organization!r}, role={role!r}; found {len(role_matches)}."
        )

    role_item = role_matches[0]

    if label:
        if role_item.get("type") != "subsections":
            raise ValueError(
                f"Role {organization!r} | {role!r} is not subsection-based, "
                f"but locator provided label={label!r}."
            )

        subsection_matches = [
            subsection
            for subsection in role_item.get("content", [])
            if subsection.get("label") == label
        ]

        if len(subsection_matches) != 1:
            raise ValueError(
                f"Expected exactly one subsection label={label!r}; "
                f"found {len(subsection_matches)}."
            )

        subsection = subsection_matches[0]

        if subsection.get("type") != "bullet":
            raise ValueError(f"Subsection label={label!r} is not type='bullet'.")

        return subsection.setdefault("content", [])

    if role_item.get("type") != "bullet":
        raise ValueError(
            f"Role {organization!r} | {role!r} is type={role_item.get('type')!r}. "
            "Provide target_locator.label for subsection-based roles."
        )

    return role_item.setdefault("content", [])


def validate_recommendation_for_apply(item: dict[str, Any]) -> None:
    priority = item.get("priority")
    action_type = item.get("action_type")

    if action_type not in {"add_role_bullet", "add_selected_project"}:
        raise ValueError(
            f"Priority {priority}: unsupported action_type for apply step: {action_type!r}"
        )

    evidence_support = item.get("evidence_support")

    if evidence_support not in ALLOWED_EVIDENCE_SUPPORT_FOR_APPLY:
        raise ValueError(
            f"Priority {priority}: evidence_support={evidence_support!r}; "
            f"allowed values are {sorted(ALLOWED_EVIDENCE_SUPPORT_FOR_APPLY)}."
        )

    if not item.get("target_locator"):
        raise ValueError(f"Priority {priority}: missing target_locator.")

    if action_type == "add_role_bullet" and not item.get("proposed_content"):
        raise ValueError(f"Priority {priority}: missing proposed_content.")

    if action_type == "add_selected_project" and not item.get("project_entry"):
        raise ValueError(
            f"Priority {priority}: add_selected_project requires project_entry."
        )


def apply_role_bullet_addition(
    resume_content: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    target_locator = item["target_locator"]

    if normalize_section_id(target_locator.get("section_id")) != "EXPERIENCE":
        raise ValueError(
            "add_role_bullet requires target_locator.section_id='EXPERIENCE'."
        )

    experience_section = get_section_by_id(resume_content, "EXPERIENCE")
    bullets = find_experience_bullet_list(experience_section, target_locator)

    status = append_unique_bullet(bullets, item["proposed_content"])

    return {
        "priority": item.get("priority"),
        "action_type": item.get("action_type"),
        "target_locator": target_locator,
        "proposed_content": item.get("proposed_content"),
        "evidence_support": item.get("evidence_support"),
        "target_relevance": item.get("target_relevance"),
        "source_evidence": item.get("source_evidence", []),
        "status": status,
    }


def apply_selected_project_addition(
    resume_content: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    target_locator = item["target_locator"]

    if normalize_section_id(target_locator.get("section_id")) != "PROJECTS":
        raise ValueError(
            "add_selected_project requires target_locator.section_id='PROJECTS'."
        )

    project_entry = deepcopy(item["project_entry"])
    projects_section = get_section_by_id(resume_content, "PROJECTS")

    if projects_section.get("type") != "subsections":
        raise ValueError("PROJECTS section must be type='subsections'.")

    project_label = project_entry.get("label")
    if not project_label:
        raise ValueError("project_entry is missing label.")

    existing_labels = {
        project.get("label")
        for project in projects_section.get("content", [])
        if isinstance(project, dict)
    }

    if project_label in existing_labels:
        status = "skipped_duplicate"
    else:
        projects_section.setdefault("content", []).append(project_entry)
        status = "added"

    return {
        "priority": item.get("priority"),
        "action_type": item.get("action_type"),
        "target_locator": target_locator,
        "project_entry": project_entry,
        "evidence_support": item.get("evidence_support"),
        "target_relevance": item.get("target_relevance"),
        "source_evidence": item.get("source_evidence", []),
        "status": status,
    }


def add_additional_content(
    *,
    base_resume_content: dict[str, Any],
    addition_recommendations: dict[str, Any],
    approved_priorities: list[int],
    base_content_version: str,
    next_content_version: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply human-approved addition recommendations."""
    updated_resume_content = deepcopy(base_resume_content)

    ranked_additions = addition_recommendations.get("ranked_additions", [])
    additions_by_priority: dict[int, dict[str, Any]] = {}

    for item in ranked_additions:
        priority = normalize_priority(item.get("priority"))
        if priority in additions_by_priority:
            raise ValueError(f"Duplicate recommendation priority found: {priority}")
        additions_by_priority[priority] = item

    approved_priorities = [normalize_priority(priority) for priority in approved_priorities]

    missing_priorities = [
        priority
        for priority in approved_priorities
        if priority not in additions_by_priority
    ]

    if missing_priorities:
        available_priorities = sorted(additions_by_priority)
        raise ValueError(
            f"Approved priorities not found in recommendations: {missing_priorities}. "
            f"Available priorities: {available_priorities}."
        )

    applied_changes = []

    for priority in approved_priorities:
        item = additions_by_priority[priority]
        validate_recommendation_for_apply(item)

        if item["action_type"] == "add_role_bullet":
            change = apply_role_bullet_addition(updated_resume_content, item)

        elif item["action_type"] == "add_selected_project":
            change = apply_selected_project_addition(updated_resume_content, item)

        else:
            raise ValueError(f"Unsupported action_type: {item['action_type']!r}")

        applied_changes.append(change)

    revision_log = {
        "revision_type": "add_additional_content",
        "base_content_version": base_content_version,
        "next_content_version": next_content_version,
        "approved_priorities": approved_priorities,
        "applied_change_count": sum(
            1 for change in applied_changes if change["status"] == "added"
        ),
        "skipped_duplicate_count": sum(
            1 for change in applied_changes if change["status"] == "skipped_duplicate"
        ),
        "applied_changes": applied_changes,
    }

    return updated_resume_content, revision_log


def display_addition_recommendations(addition_recommendations: dict[str, Any]) -> None:
    """Print ranked addition recommendations in a readable review format."""
    ranked = addition_recommendations.get("ranked_additions", [])

    print("=" * 100)
    print("ADDITION RECOMMENDATIONS")
    print("=" * 100)

    if addition_recommendations.get("overall_recommendation"):
        print(addition_recommendations["overall_recommendation"])
        print()

    if not ranked:
        print("No ranked additions found.")
        return

    for item in ranked:
        priority = item.get("priority")
        action_type = item.get("action_type")
        target = item.get("target")
        relevance = item.get("target_relevance")
        evidence_support = item.get("evidence_support")
        space = item.get("estimated_space_cost")
        redundancy = item.get("redundancy_risk")
        confidence = item.get("confidence")

        print("-" * 100)
        print(f"[{priority}] {action_type} -> {target}")
        print(
            f"relevance={relevance} | evidence={evidence_support} | "
            f"space={space} | redundancy={redundancy} | confidence={confidence}"
        )

        if action_type == "add_role_bullet":
            print("\nProposed bullet:")
            print(f"- {item.get('proposed_content', '')}")

        elif action_type == "add_selected_project":
            project_entry = item.get("project_entry") or {}
            print("\nProposed project:")
            print(project_entry.get("label", ""))
            for bullet in project_entry.get("content", []):
                print(f"- {bullet}")

        if item.get("target_signals_strengthened"):
            print("\nSignals strengthened:")
            for signal in item["target_signals_strengthened"]:
                print(f"- {signal}")

        if item.get("why_this_adds_signal"):
            print("\nWhy this adds signal:")
            print(item["why_this_adds_signal"])

        if item.get("why_not_another_option"):
            print("\nWhy not another option:")
            print(item["why_not_another_option"])

        if item.get("source_evidence"):
            print("\nSource evidence:")
            for evidence in item["source_evidence"]:
                evidence_id = evidence.get("evidence_id", "")
                statement = evidence.get("evidence_statement", "")
                print(f"- {evidence_id}: {statement}")

    print("-" * 100)
