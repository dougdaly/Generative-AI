from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import hashlib, json, os, sys, time, subprocess, signal
import uuid
import httpx
import requests

# SERVER LAUNCHING CODE
import requests

def sha256_json_bytes(obj: Any) -> str:
    b = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def wait_http_ok(url: str, timeout_s: int = 20, poll_s: float = 0.25) -> None:
    t0 = time.time()
    last_err = None
    while time.time() - t0 < timeout_s:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            last_err = repr(e)
        time.sleep(poll_s)
    raise RuntimeError(f"Timed out waiting for {url}. Last error: {last_err}")

def start_uvicorn(app_spec, host, port, *, cwd=None, env=None, app_dir=None):
    cmd = [sys.executable, "-m", "uvicorn"]

    if app_dir is not None:
        cmd += ["--app-dir", str(app_dir)]

    cmd += [app_spec, "--host", host, "--port", str(port), "--log-level", "info"]

    return subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **(env or {})},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

def tail(proc: subprocess.Popen, n: int = 30) -> str:
    # best-effort: grab a few log lines if needed for debugging
    if not proc.stdout:
        return ""
    lines = []
    for _ in range(n):
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line.rstrip())
    return "\n".join(lines)

def stop_proc(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        proc.kill()



def extract_answer_text(res) -> str:
    """
    Accepts either:
      - AgentResult (preferred)
      - raw A2A task-result dict (fallback)
    Returns the best-effort text payload.
    """
    # Preferred: AgentResult
    if isinstance(res, AgentResult):
        out = res.output
        if isinstance(out, str):
            return out.strip()
        if isinstance(out, dict):
            # sometimes output may already be parsed JSON
            return json.dumps(out, ensure_ascii=False)
        # last resort
        return str(out).strip()

    # Fallback: raw dict task result
    task_result = res
    art = task_result["artifacts"][0]
    part = art["parts"][0]

    if part.get("kind") == "text":
        return (part.get("text") or "").strip()

    # If it's a data artifact, serialize it
    if part.get("kind") == "data" and "data" in part:
        return json.dumps(part["data"], ensure_ascii=False)

    raise KeyError(f"Unsupported artifact part: {part}")



# AGENT CLASSES

@dataclass(frozen=True)
class AgentCard:
    """Metadata about an A2A agent. Frozen is true to make hashable."""
    name: str
    url: str
    skills: list[str]                  # keep simple: list of skill ids/strings
    raw: dict[str, Any]                # original JSON card
    card_sha256: str                   # hash of raw JSON for reproducibility
    version: Optional[str] = None      # optional version string


@dataclass
class AgentResult:
    output: Any                        # raw agent output (text or dict)
    meta: dict[str, Any]               # provenance: agent name, model, llm_calls, tools, etc.
    raw: dict[str, Any] | None = None  # raw A2A task result for debugging


@dataclass
class Score:
    ok: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    id: str
    description: str
    prompt: str
    needed_skills: list[str]
    score_fn: Callable[[AgentResult], Score]
    contract: str = ""
    kind: str = ""   # optional, but handy for reporting

class Agent:
    """A generic agent which runs via the invoke method."""
    def __init__(self, card: AgentCard):
        self.card = card

    def invoke(self, prompt: str) -> AgentResult:
        raise NotImplementedError


def _require_meta(meta: dict[str, Any], *, where: str):
    '''Ensure required provenance keys are present in meta.'''
    required = ["agent_name", "card_sha256", "llm_calls", "tools_used", "schema_validated", "stub_hit"]
    missing = [k for k in required if k not in meta]
    if missing:
        raise RuntimeError(f"{where}: missing provenance keys: {missing}")

def _extract_first_output(task_result: dict):
    for art in task_result.get("artifacts", []) or []:
        for part in art.get("parts", []) or []:
            k = part.get("kind")
            if k == "data" and "data" in part:
                return part["data"]          # <-- native Python object
            if k == "text" and part.get("text"):
                return part["text"]
    return None

# a2a_core.py
import httpx, uuid

class A2AHttpAgent(Agent):
    def __init__(self, card: AgentCard, *, timeout_s: int = 120):
        super().__init__(card)
        self.timeout_s = timeout_s

    def invoke(self, prompt: str) -> AgentResult:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {
                "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}
            },
        }

        timeout = httpx.Timeout(
            self.timeout_s,
            connect=10.0,
            read=self.timeout_s,
            write=10.0,
            pool=10.0,
        )

        r = httpx.post(f"{self.card.url}/a2a", json=payload, timeout=timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} from {self.card.url}/a2a:\n{r.text}")
        resp = r.json()
        if "error" in resp:
            raise RuntimeError(f"invoke({self.card.name}): JSON-RPC error:\n{resp['error']}")
        if "result" not in resp:
            raise RuntimeError(f"invoke({self.card.name}): malformed response, missing 'result':\n{resp}")
        task_result = resp["result"]


        # Extract “output” from first artifact in a tolerant way
        output = _extract_first_output(task_result)
        try:
            art = (task_result.get("artifacts") or [])[0]
            part = (art.get("parts") or [])[0]
            if part.get("kind") == "data" and "data" in part:
                output = part["data"]
            elif part.get("kind") == "text":
                output = part.get("text", "")
        except Exception:
            pass

        # Agents must include meta, or strict mode fails.
        meta = task_result.get("meta", {})
        meta.setdefault("agent_name", self.card.name)
        meta.setdefault("card_sha256", self.card.card_sha256)

        _require_meta(meta, where=f"invoke({self.card.name})")

        return AgentResult(output=output, meta=meta, raw=task_result)

class AgentRegistry:
    def __init__(self, cards: list[AgentCard]):
        self.cards = cards
        self.by_name = {c.name: c for c in cards}

    def get_agent(self, needed_skills: list[str], *, fallback_name: str) -> AgentCard:
        # select first agent that satisfies all required skills
        for c in self.cards:
            if all(s in c.skills for s in needed_skills):
                return c
        return self.by_name[fallback_name]

    def describe_agent(self, card: AgentCard) -> str:
        return f"{card.name} @ {card.url}\nskills: {', '.join(card.skills)}\ncard_sha256: {card.card_sha256[:10]}..."

def fetch_agent_card(url: str) -> AgentCard:
    r = requests.get(f"{url}/.well-known/agent.json", timeout=5)
    r.raise_for_status()
    raw = r.json()

    sha = raw.get("card_sha256") or sha256_json_bytes({k: raw[k] for k in ("name","version","url","skills") if k in raw})

    skills = []
    for s in raw.get("skills", []):
        if isinstance(s, str):
            skills.append(s)
        elif isinstance(s, dict):
            skills.append(s.get("id") or s.get("name") or str(s))
        else:
            skills.append(str(s))

    return AgentCard(
        name=raw.get("name", url),
        url=raw.get("url", url),          # prefer card url if present
        skills=skills,
        raw=raw,
        card_sha256=sha,
    )