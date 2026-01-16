# story_agent.py
import os
import re
import time
from typing import Any, Callable, Dict, List, Tuple

import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]  # adjust if needed
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from a2a.core import (
    AgentCard,
)
from a2a.server import (
    run_with_tools,
    create_a2a_app,
    build_task_result,
)


AGENT_NAME = "story"
AGENT_VERSION = "0.1.0"
AGENT_URL = os.getenv("STORY_AGENT_URL", "http://127.0.0.1:8103")
MODEL = os.getenv("STORY_MODEL", os.getenv("GENERALIST_MODEL", "gpt-4o-mini"))

CARD = AgentCard(
    name=AGENT_NAME,
    version=AGENT_VERSION,
    url=AGENT_URL,
    skills=["story.parse", "story.check"],
    raw={},
    card_sha256="",
)

SYSTEM_STORY = """You are a Story Builder Specialist.

You will receive a single user prompt that includes all requirements.
You have tools to:
- Parse the prompt into a contract (hard facts, chapter rules, clue marker rules, word limit).
- Check whether a draft satisfies the contract.

Process (MUST follow):
1) Call tool_parse_story_contract(prompt_text=the_user_prompt) once and read the contract.
2) Draft the full story.
3) Call tool_check_story(draft_text=your_draft, contract=the_contract).
4) If not ok, revise the story to fix ONLY the reported issues, then re-check.
5) Repeat until ok or you hit the tool-loop limit.
6) When ok, output ONLY the final story text (no JSON, no markdown, no commentary).

Hard rules:
- Do not invent new constraints. Use only what is in the user prompt/contract.
- Keep the noir style, but do not sacrifice contract compliance.
- You may call tool_check_story at most 2 times. If still failing after 2 attempts, output the best draft and stop.
"""

# --- Tools schema (Responses API) ---
TOOLS_STORY: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "tool_parse_story_contract",
        "description": "Parse a story prompt into a contract: chapter count, word limit, hard facts, clue marker rules, and any explicit requirements.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt_text": {"type": "string"},
            },
            "required": ["prompt_text"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "tool_check_story",
        "description": "Check a drafted story against the parsed contract. Returns ok + list of issues.",
        "parameters": {
            "type": "object",
            "properties": {
                "draft_text": {"type": "string"},
                "contract": {"type": "object"},
            },
            "required": ["draft_text", "contract"],
            "additionalProperties": False,
        },
    },
]


_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with", "as",
    "is", "are", "was", "were", "be", "been", "being", "that", "this", "these", "those",
    "must", "remain", "true", "across", "all", "chapters", "chapter", "exactly", "only",
}

def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s))

def _extract_hard_facts(prompt_text: str) -> List[Dict[str, Any]]:
    """
    Extract lines like:
      F1) ...
      F2) ...
    and build "anchors" (keywords) for each fact.
    """
    facts: List[Dict[str, Any]] = []
    for m in re.finditer(r"^\s*F(\d+)\)\s*(.+?)\s*$", prompt_text, flags=re.MULTILINE):
        fid = f"F{m.group(1)}"
        text = m.group(2).strip()

        # Strong anchors: quoted phrases, ALLCAPS tokens, Proper Noun phrases
        quoted = re.findall(r"[\"“”']([^\"“”']+)[\"“”']", text)
        allcaps = re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text)
        proper = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text)

        # Weak anchors: longer tokens (minus stopwords)
        toks = re.findall(r"[A-Za-z0-9_]+", text)
        weak = []
        for t in toks:
            tl = t.lower()
            if tl in _STOPWORDS:
                continue
            if len(tl) >= 5 or t.isdigit():
                weak.append(t)

        anchors = []
        for group in (quoted, allcaps, proper, weak):
            for a in group:
                a = a.strip()
                if not a:
                    continue
                if a.lower() not in {x.lower() for x in anchors}:
                    anchors.append(a)

        # Require a few anchors, not all.
        required_hits = 1 if len(anchors) <= 2 else min(3, max(2, len(anchors) // 3))

        facts.append({
            "id": fid,
            "text": text,
            "anchors": anchors[:12],
            "required_hits": required_hits,
        })
    return facts

DEFAULT_CLUE_MARKER = "NEW CLUE:"
def tool_parse_story_contract(*, prompt_text: str) -> Dict[str, Any]:
    # Chapter count
    chapter_count = 3
    m = re.search(r"EXACTLY\s+(\d+)\s+chapters", prompt_text, flags=re.IGNORECASE)
    if m:
        try:
            chapter_count = int(m.group(1))
        except Exception:
            chapter_count = 3

    # Word limit (accept "under 1,200 words", "under 1200 words", etc)
    word_limit = None
    m = re.search(r"under\s+([\d,]+)\s+words", prompt_text, flags=re.IGNORECASE)
    if m:
        try:
            word_limit = int(m.group(1).replace(",", ""))
        except Exception:
            word_limit = None

    clue_marker = None
    if re.search(r"NEW CLUE:", prompt_text):
        clue_marker = "NEW CLUE:"
    # If prompt says "exactly one NEW clue per chapter", we enforce 1/chapter
    clues_per_chapter = 1 if clue_marker else 0
    if isinstance(clue_marker, str):
        clue_marker = clue_marker.strip() or DEFAULT_CLUE_MARKER
    else:
        clue_marker = DEFAULT_CLUE_MARKER
    hard_facts = _extract_hard_facts(prompt_text)

    # Require Chapter 3 explanation if prompt includes language like this
    require_explain = bool(re.search(r"Chapter\s*3.*explain", prompt_text, flags=re.IGNORECASE))

    return {
        "chapter_count": chapter_count,
        "word_limit": word_limit,
        "hard_facts": hard_facts,
        "clue_marker": clue_marker,
        "clues_per_chapter": clues_per_chapter,
        "require_ch3_explain": require_explain,
    }

def _split_chapters(draft_text: str) -> Tuple[Dict[int, str], List[Dict[str, Any]]]:
    issues: List[Dict[str, Any]] = []
    matches = list(re.finditer(r"^Chapter\s+(\d+)\b.*$", draft_text, flags=re.MULTILINE))
    if not matches:
        return {}, [{"code": "no_chapters", "severity": "error", "msg": "No 'Chapter N' headings found."}]

    chapters: Dict[int, str] = {}
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(draft_text)
        body = draft_text[start:end].strip()
        chapters[n] = body

    return chapters, issues

def tool_check_story(*, draft_text: str, contract: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}

    chapter_count = int(contract.get("chapter_count") or 3)
    word_limit = contract.get("word_limit")
    hard_facts = contract.get("hard_facts") or []
    clue_marker = contract.get("clue_marker")
    clues_per_chapter = contract.get("clues_per_chapter")
    require_ch3_explain = bool(contract.get("require_ch3_explain"))

    # Word limit
    wc = _word_count(draft_text)
    stats["word_count"] = wc
    if isinstance(word_limit, int) and wc > word_limit:
        issues.append({"code": "word_limit", "severity": "error", "msg": f"Word count {wc} exceeds limit {word_limit}."})

    # Chapters
    chapters, chap_issues = _split_chapters(draft_text)
    issues.extend(chap_issues)

    stats["chapters_found"] = sorted(chapters.keys())
    if chapters:
        if len(chapters) != chapter_count:
            issues.append({
                "code": "chapter_count",
                "severity": "error",
                "msg": f"Expected {chapter_count} chapters, found {len(chapters)} ({sorted(chapters.keys())})."
            })
        # Require chapters 1..N
        expected = list(range(1, chapter_count + 1))
        if sorted(chapters.keys()) != expected:
            issues.append({
                "code": "chapter_labels",
                "severity": "error",
                "msg": f"Expected chapter labels {expected}, found {sorted(chapters.keys())}."
            })

    # NEW CLUE lines
    if clue_marker and chapters:
        total_clues = len(re.findall(rf"^{re.escape(clue_marker)}\s*.+$", draft_text, flags=re.MULTILINE))
        stats["total_clues"] = total_clues

        expected_total = chapter_count * int(clues_per_chapter or 1)
        if total_clues != expected_total:
            issues.append({
                "code": "clue_total",
                "severity": "error",
                "msg": f"Expected {expected_total} '{clue_marker}' lines total, found {total_clues}."
            })

        for n in range(1, chapter_count + 1):
            body = chapters.get(n, "")
            per = len(re.findall(rf"^{re.escape(clue_marker)}\s*.+$", body, flags=re.MULTILINE))
            if per != int(clues_per_chapter or 1):
                issues.append({
                    "code": "clue_per_chapter",
                    "severity": "error",
                    "where": f"chapter_{n}",
                    "msg": f"Chapter {n} must contain exactly {clues_per_chapter} '{clue_marker}' line(s), found {per}."
                })

    # Hard facts (anchor matching)
    lower = draft_text.lower()
    missed: List[str] = []
    for f in hard_facts:
        anchors: List[str] = f.get("anchors") or []
        need = int(f.get("required_hits") or 1)
        hits = 0
        for a in anchors:
            if a.lower() in lower:
                hits += 1
        if hits < need:
            missed.append(f.get("id") or "?")
            issues.append({
                "code": "hard_fact_missing",
                "severity": "error",
                "msg": f"Hard fact {f.get('id')} not satisfied (hits {hits}/{need}). Anchors tried: {anchors[:8]}",
            })
    stats["missed_facts"] = missed

    # Chapter 3 explanation heuristic
    if require_ch3_explain and chapters:
        ch3 = chapters.get(3, "")
        # Heuristic: should include at least one causal/explanatory signal (Currently does not work)
        #explain_signals = ["how it worked", "the trick", "the method", "because", "therefore", "so the", "that’s how"]
        if 0: #not any(s in ch3.lower() for s in explain_signals):
            issues.append({
                "code": "ch3_explain",
                "severity": "error",
                "where": "chapter_3",
                "msg": "Chapter 3 does not clearly explain the 'impossible' method (no explanatory signals found)."
            })

    ok = len([i for i in issues if i.get("severity") == "error"]) == 0
    return {
        "ok": ok,
        "issue_count": len(issues),
        "issues": issues[:12],   # cap it
        "stats": {
            "word_count": wc,
            "chapter_count_found": len(chapters),
            "clue_counts": {n: len(re.findall(rf"^{re.escape(clue_marker)}\s*.+$", chapters.get(n, ""), flags=re.MULTILINE)) for n in chapters},
        }
    }


TOOL_IMPL_STORY: Dict[str, Callable[..., Any]] = {
    "tool_parse_story_contract": tool_parse_story_contract,
    "tool_check_story": tool_check_story,
}


def brain(prompt_text: str) -> Dict[str, Any]:
    t0 = time.time()

    # 1) Draft (no tools)
    txt, meta = run_with_tools(
        model=MODEL,
        system=SYSTEM_STORY,
        user=prompt_text,
        tools=[],
        tool_impl={},
        max_rounds=1,
    )

    # 2) Deterministic check
    contract = tool_parse_story_contract(prompt_text=prompt_text)
    check = tool_check_story(draft_text=txt, contract=contract)

    # 3) One repair pass if needed (still no tools)
    if not check.get("ok"):
        issues = check.get("issues", [])
        repair_prompt = (
            prompt_text
            + "\n\nThe draft failed these checks. Revise ONCE and satisfy all constraints:\n"
            + "\n".join(f"- {x}" for x in issues[:12])  # cap list
            + "\n\nReturn story text only."
        )
        txt2, meta2 = run_with_tools(
            model=MODEL,
            system=SYSTEM_STORY,
            user=repair_prompt,
            tools=[],
            tool_impl={},
            max_rounds=1,
        )
        txt = txt2
        meta = {**(meta or {}), **(meta2 or {}), "repair_pass": True}

        # re-check (still deterministic)
        check = tool_check_story(draft_text=txt, contract=contract)

    meta = dict(meta or {})
    meta.update({
        "agent": AGENT_NAME,
        "agent_version": AGENT_VERSION,
        "model": MODEL,
        "schema_validated": bool(check.get("ok")),
        "stub_hit": False,
        "latency_ms": int((time.time() - t0) * 1000),
        "checker_stats": check.get("stats", {}),
        "checker_issue_count": len(check.get("issues", [])),
    })

    return build_task_result(
        artifact_name="story.txt",
        parts=[{"kind": "text", "text": txt}],
        meta=meta,
    )



app = create_a2a_app(CARD, brain)
