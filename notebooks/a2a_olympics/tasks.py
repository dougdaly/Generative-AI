import json, math, re
from .a2a_core import extract_answer_text, AgentResult
from .story_agent import tool_parse_story_contract, tool_check_story
from typing import Any, Dict, Tuple

# TASK INFORMATION -- PROMPTS & CONTRACTS
# Info for task 1
TASK1_NUM_SOLUTIONS = 10
TASK1_PROMPT = """Solve for real x.

Equation:
  sin(x) = x/20

Requirements:
- Return the 10 real solutions with the smallest |x|.
- Exclude x = 0.
- A solution is valid only if |sin(x) - x/20| <= 1e-10.
- Solutions must be unique within 1e-8.
- Sort by (|x|, x) ascending.
- Output ONLY JSON: a list of objects [{"re": <float>, "im": 0.0}, ...] and nothing else.
"""
TASK1_CONTRACT = f"""
Solve the given equation for x over the real numbers.

Return ONLY JSON. No prose, no markdown.

Output format:
- A JSON array of exactly {TASK1_NUM_SOLUTIONS} objects.
- Each object has:
  - "re": number
  - "im": number

Selection & ordering:
- Return the {TASK1_NUM_SOLUTIONS} solutions with smallest absolute value |x|.
- Sort by increasing |x|, tie-breaker: increasing x.
- No duplicates: treat x_i and x_j as the same if |x_i - x_j| < 1e-10.

Verification:
- For each item, interpret x = re + i*im.
- Must satisfy:
  - |sin(x) - x/20| <= 1e-10
  - abs(im) < 1e-10 (and set "im" to 0.0 exactly)"""


# Info for task 2
TASK2_DATA = (
  '2026-01-05T20:12:10.123Z | level=ERROR | svc=billing | request_id=9f2c1c3f-6d4d-4f2a-9a2e-2a9b2f2f1c11 '
  '| user=U123 | ip=203.0.113.8 | amount_usd=19.99 | retry=2 | test=false '
  '| tags=[checkout, card, "first purchase"] '
  '| err={"code":"INSUFF_FUNDS","provider":"stripe","decline_code":"insufficient_funds"} '
  '| msg="charge failed: insufficient_funds"'
)
TASK2_SCHEMA = {
  "type": "object",
  "additionalProperties": False,
  "properties": {
    "timestamp": {"type": "string"},
    "level": {"type": "string", "enum": ["DEBUG","INFO","WARN","ERROR"]},
    "service": {"type": "string"},

    "request": {
      "type": "object",
      "additionalProperties": False,
      "properties": {
        "id": {"type": "string"},
        "ip": {"type": "string"},
      },
      "required": ["id"]
    },

    "user": {
      "type": "object",
      "additionalProperties": False,
      "properties": {"id": {"type": "string"}},
      "required": ["id"]
    },

    "payment": {
      "type": "object",
      "additionalProperties": False,
      "properties": {
        "amount": {"type": "number"},
        "currency": {"type": "string", "enum": ["USD","EUR"]},
        "retry_count": {"type": "integer"},
        "is_test": {"type": "boolean"},
      },
      "required": ["amount","currency"]
    },

    "error": {
      "type": "object",
      "additionalProperties": False,
      "properties": {
        "code": {"type": "string"},
        "provider": {"type": "string"},
        "decline_code": {"type": "string"},
      },
      "required": ["code"]
    },

    "tags": {"type": "array", "items": {"type": "string"}},
    "message": {"type": "string"},
  },
  "required": ["timestamp","level","service","request","user","payment","error","message"]
}

TASK2_PROMPT = f"""\
Extract a JSON object from the log line that conforms to the JSON Schema.
Return ONLY the JSON object. No markdown. No commentary.

DATA:
{TASK2_DATA}

SCHEMA:
{json.dumps(TASK2_SCHEMA)}
"""
TASK2_CONTRACT = """\
You MUST output a single JSON object that conforms to the provided JSON Schema.

Hard requirements:
- Output is valid JSON (no markdown, no code fences).
- Output is an object (not a list).
- Output validates against the schema:
  - additionalProperties: false
  - required keys present: timestamp, level, service, message

Scoring:
- 0 if invalid JSON or schema validation fails.
- Base score 10 if valid.
- +0.5 bonus if user_id extracted correctly (U123).
- +0.5 bonus if error_code extracted correctly (INSUFF_FUNDS).
"""

# Info for task 3
TASK3_PROMPT = """
Write a 1950s hard-boiled detective noir story in EXACTLY 3 chapters.
Tone: smoky, cynical, sharp metaphors, streetwise dialogue.

Premise:
A private detective (name: Sam Slate) investigates a murder that appears impossible.

Hard facts that MUST remain true across all 3 chapters:
F1) The victim is Lionel Crane, a watchmaker.
F2) The body is found inside a locked walk-in safe; the safe door is locked from the outside.
F3) The only physical evidence at the scene is a damp matchbook labeled “BLUE LAGOON” and a smear of red sealing wax.
F4) The detective’s injured left hand shakes whenever he lies.
F5) The murderer is revealed to be Captain Rourke, a respected harbor master, and the motive is insurance fraud tied to smuggling.

Structure requirements:
- Label chapters as “Chapter 1”, “Chapter 2”, “Chapter 3”.
- Each chapter must introduce exactly one NEW clue (so 3 total new clues; do not add more).
- Each chapter must contain exactly one clue line that starts with NEW CLUE: (exact text)
- Chapter 3 must explain the “impossible” method clearly and logically.
- Do not introduce supernatural elements.
- Keep it under 1,200 words total.

Output: story text only."""


TASK3_CONTRACT = """\
Task 3: 1950s hard-boiled noir story in EXACTLY 3 chapters.

Hard requirements:
- Chapters are labeled exactly: "Chapter 1", "Chapter 2", "Chapter 3" (one each, in order).
- Total length under 1,200 words.
- No supernatural elements.
- Hard facts F1..F5 must remain true across the full story.
- Each chapter introduces exactly one new clue:
  - Each chapter must contain exactly one line starting with "NEW CLUE: "
  - The NEW CLUE line must be a single sentence.
  - No other NEW CLUE lines in the story.
- Chapter 3 must explain the “impossible” method clearly and logically.

Scoring (max 10):
- Structure (chapters + word limit): 2.0
- Hard facts F1..F5: 5.0 (1 point each)
- Clues: 3.0 (1 point per chapter for exactly one NEW CLUE line, +0 bonus if unique enforced by checker)
- 0 if output is empty or not text.
"""



# SCORING MECHANISMS
# Scoring for task 1
def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        # drop first fence line and last fence if present
        s = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", s)
        s = re.sub(r"\n```$", "", s.strip())
    return s.strip()

def _coerce_roots(output: Any):
    if isinstance(output, list):
        return output
    if isinstance(output, str):
        s = _strip_code_fences(output)
        return json.loads(s)
    raise TypeError(f"Unexpected output type: {type(output)}")

def score_task1(res: AgentResult) -> dict:
    try:
        roots = _coerce_roots(res.output)
    except Exception as e:
        snippet = (res.output[:120] if isinstance(res.output, str) else str(res.output)[:120])
        return {"score": 0.0, "summary": {"error": f"JSON parse failed: {type(e).__name__}: {e}", "text_snippet": snippet}}

    if not isinstance(roots, list):
        return {"score": 0.0, "summary": {"error": "Output must be a JSON list"}}

    xs = []
    for z in roots:
        if not isinstance(z, dict) or "re" not in z or "im" not in z:
            return {"score": 0.0, "summary": {"error": "Items must be objects with re/im"}}
        re_ = z["re"]; im_ = z["im"]
        if not isinstance(re_, (int,float)) or not isinstance(im_, (int,float)):
            return {"score": 0.0, "summary": {"error": "re/im must be numbers"}}
        if abs(im_) > 1e-10:
            return {"score": 0.0, "summary": {"error": "imaginary parts must be ~0"}}
        xs.append(float(re_))

    # residuals
    resid = [abs(math.sin(x) - x/20.0) for x in xs]
    n_good = sum(1 for r in resid if r <= 1e-10)

    return {"score": min(10.0, float(n_good)), "summary": {"residuals": resid}}


# Scoring for task 2
def _validate_jsonschema(obj: dict, schema: dict) -> tuple[bool, list[str]]:
    try:
        from jsonschema import Draft7Validator
    except Exception as e:
        raise RuntimeError("Missing dependency: jsonschema (pip install jsonschema)") from e

    v = Draft7Validator(schema)
    errs = [err.message for err in v.iter_errors(obj)]
    return (len(errs) == 0, errs)


def score_task2(res: AgentResult) -> dict:
    obj = res.output
    if isinstance(obj, str):
        s = obj.strip()
        try:
            obj = json.loads(s)
        except Exception as e:
            return {"score": 0.0, "summary": {"error": f"JSON parse failed: {type(e).__name__}: {e}", "snippet": s[:220]}}

    if not isinstance(obj, dict):
        return {"score": 0.0, "summary": {"error": "Output must be a JSON object", "type": str(type(obj))}}

    ok, errors = _validate_jsonschema(obj, TASK2_SCHEMA)
    if not ok:
        return {"score": 0.0, "summary": {"error": "Schema validation failed", "errors": errors}}

    # Field-level accuracy (max 12 here)
    checks = {
        "timestamp": (obj.get("timestamp") == "2026-01-05T20:12:10.123Z"),
        "level": (obj.get("level") == "ERROR"),
        "service": (obj.get("service") == "billing"),
        "request.id": (obj.get("request", {}).get("id") == "9f2c1c3f-6d4d-4f2a-9a2e-2a9b2f2f1c11"),
        "request.ip": (obj.get("request", {}).get("ip") == "203.0.113.8"),
        "user.id": (obj.get("user", {}).get("id") == "U123"),
        "payment.amount": (abs(obj.get("payment", {}).get("amount", 0) - 19.99) < 1e-9),
        "payment.currency": (obj.get("payment", {}).get("currency") == "USD"),
        "payment.retry_count": (obj.get("payment", {}).get("retry_count") == 2),
        "payment.is_test": (obj.get("payment", {}).get("is_test") is False),
        "error.code": (obj.get("error", {}).get("code") == "INSUFF_FUNDS"),
        "message": (obj.get("message") == "charge failed: insufficient_funds"),
    }

    score = float(sum(checks.values()))
    return {"score": score, "summary": {"valid": True, "checks": checks, "output": obj}}



# Scoring for task 3
# these helpers may be useful in a future scoring mechanism
def _get_story_text(res) -> str:
    """
    Accepts AgentResult or raw dict-ish outputs.
    """
    # If it's your AgentResult dataclass
    if hasattr(res, "output"):
        out = res.output
        if isinstance(out, str):
            return out.strip()

        # Try to pull text from raw artifacts if present
        raw = getattr(res, "raw", None)
        if isinstance(raw, dict):
            return _extract_from_a2a_raw(raw).strip()

        # If output is already dict-like A2A payload
        if isinstance(out, dict):
            return _extract_from_a2a_raw(out).strip()

        return str(out).strip()

    # Raw dict
    if isinstance(res, dict):
        return _extract_from_a2a_raw(res).strip()

    return str(res).strip()


def _extract_from_a2a_raw(task_result: dict) -> str:
    """
    Handles either:
      {"artifacts":[{"parts":[{"kind":"text","text":"..."}]}]}
    or your wrapper shapes.
    """
    # Some code paths pass {"result": {...}}
    if "result" in task_result and isinstance(task_result["result"], dict):
        task_result = task_result["result"]

    arts = task_result.get("artifacts") or []
    if not arts:
        return ""

    parts = (arts[0].get("parts") or [])
    if not parts:
        return ""

    p0 = parts[0]
    if p0.get("kind") == "text":
        return p0.get("text", "") or ""
    # If someone returned data accidentally, stringify it
    if p0.get("kind") == "data":
        return json.dumps(p0.get("data"), ensure_ascii=False)

    return ""


def _split_chapters(story: str) -> Tuple[Dict[int, str], Dict[str, Any]]:
    """
    Returns (chapters, info). chapters[n] is chapter body text.
    """
    info = {"errors": []}
    matches = list(re.finditer(r"^Chapter\s+(\d+)\s*$", story, flags=re.MULTILINE))
    if not matches:
        info["errors"].append("No chapter headings found.")
        return {}, info

    chapters: Dict[int, str] = {}
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(story)
        chapters[n] = story[start:end].strip()

    return chapters, info


def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s))


def _has_supernatural(story_lower: str) -> bool:
    bad = [
        "ghost", "specter", "spirit", "haunt", "vampire", "werewolf", "witch",
        "magic", "spell", "curse", "demon", "supernatural", "paranormal",
        "time travel", "teleport", "necromanc", "eldritch",
    ]
    return any(w in story_lower for w in bad)


def _fact_checks(story: str, chapters: Dict[int, str]) -> Dict[str, bool]:
    s = story.lower()

    # F1: Lionel Crane + watchmaker
    f1 = ("lionel crane" in s) and ("watchmaker" in s or "watch-maker" in s)

    # F2: walk-in safe + locked from outside
    f2 = ("walk-in safe" in s or "walk in safe" in s) and ("locked from the outside" in s or "locked from outside" in s)

    # F3: matchbook BLUE LAGOON + red sealing wax + only physical evidence (we check core props)
    f3 = ("matchbook" in s) and ("blue lagoon" in s) and ("sealing wax" in s) and ("red" in s)

    # F4: Sam Slate + injured left hand + shakes when lies
    f4 = ("sam slate" in s) and ("left hand" in s) and ("shake" in s) and ("lie" in s)

    # F5: Captain Rourke + harbor master + insurance fraud + smuggling (prefer in Chapter 3 but accept anywhere)
    ch3 = chapters.get(3, "").lower()
    f5 = (
        ("captain rourke" in s)
        and ("harbor master" in s or "harbour master" in s)
        and ("insurance fraud" in s or ("insurance" in s and "fraud" in s))
        and ("smuggl" in s)
    )

    return {"F1": f1, "F2": f2, "F3": f3, "F4": f4, "F5": f5}


def _check_explanation(chapters: Dict[int, str]) -> bool:
    ch3 = chapters.get(3, "")
    if not ch3:
        return False

    s = ch3.lower()
    # Must contain explanation-ish language + tie to the core constraints
    explain_signals = ["how it worked", "the trick", "the method", "because", "therefore", "that’s how", "thats how", "so the"]
    ties_to_scene = ["walk-in safe", "walk in safe", "locked from", "blue lagoon", "sealing wax", "matchbook"]

    return (any(x in s for x in explain_signals) and sum(1 for t in ties_to_scene if t in s) >= 2)


def _count_clues(ch_body: str) -> int:
    # Objective marker
    n = len(re.findall(r"^NEW CLUE:\s*.+$", ch_body, flags=re.MULTILINE))
    if n:
        return n

    # Weak fallback: accept "New clue:" or "CLUE:" lines
    n2 = len(re.findall(r"^(New clue:|CLUE:)\s*.+$", ch_body, flags=re.MULTILINE | re.IGNORECASE))
    return n2

def score_task3(res: AgentResult) -> dict:
    text = res.output if isinstance(res.output, str) else str(res.output)

    contract = tool_parse_story_contract(prompt_text=TASK3_CONTRACT)  # or res.meta["task_prompt"] if you store it
    check = tool_check_story(draft_text=text, contract=contract)

    if not check.get("ok"):
        return {"score": 0.0, "summary": check}

    # Optional: give partial credit based on counts
    return {"score": 10.0, "summary": check}

# Future score_task3 -- more sophisticated scoring breakdown
def score_task3_in_work(res: AgentResult, *, task_prompt: str) -> dict:
    text = res.output
    if not isinstance(text, str) or not text.strip():
        return {"score": 0.0, "summary": {"error": "Empty/non-text output"}}

    contract = tool_parse_story_contract(prompt_text=task_prompt)
    check = tool_check_story(draft_text=text, contract=contract)

    stats = check.get("stats", {}) or {}
    facts = (stats.get("facts", {}) or {})

    # Structure: chapters + word limit
    structure = 0.0
    expected_n = contract.get("chapter_count", 3)
    if stats.get("chapter_count_found") == expected_n:
        structure += 1.0
    if stats.get("word_count", 10**9) <= contract.get("max_words", 1200):
        structure += 1.0

    # Facts: 1 point each
    fact_score = 0.0
    for fid, fr in facts.items():
        if fr.get("ok"):
            fact_score += 1.0

    # Clues: 1 point per chapter if marker required + exactly 1 line
    clue_score = 0.0
    clue_cfg = contract.get("clue", {}) or {}
    if clue_cfg.get("marker_required"):
        counts = stats.get("clue_counts", [])
        for c in counts:
            if c == 1:
                clue_score += 1.0
    else:
        # If marker isn't required, you can either:
        # - give 0 here, or
        # - do a heuristic "clue" keyword scan (weak). I recommend 0 to keep integrity.
        clue_score = 0.0

    score = min(10.0, structure + fact_score + clue_score)

    return {
        "score": float(score),
        "summary": {
            "ok": bool(check.get("ok")),
            "structure": structure,
            "fact_score": fact_score,
            "clue_score": clue_score,
            "issues": check.get("issues", []),
            "stats": stats,
        },
    }

