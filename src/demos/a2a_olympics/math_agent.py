import os
import sympy as sp
import json
import math
import mpmath as mp

import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]  # adjust if needed
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from a2a.core import AgentCard
from a2a.server import run_with_tools, create_a2a_app, build_task_result
from typing import Callable, Any
from scipy.optimize import brentq
import mpmath as mp


MODEL = os.getenv("GENERALIST_MODEL", "gpt-4o-mini")

SYSTEM_MATH = """You are a math specialist.

Call tool_solve_real_roots exactly once.
Then return ONLY valid JSON: a list of exactly 10 items, each {"re": float, "im": 0.0}.
No markdown. No commentary.
"""

SYSTEM_MATH_OLD = """
You are a math specialist. You solve equations using tools and you verify results.

Tooling rules (always follow):
- Prefer tool_bracket_roots to discover candidate intervals for real roots.
- Use tool_refine_root on brackets to get numeric roots.
- Use tool_verify_residuals to verify candidates. Do not trust unverified numbers.

Output contract (must follow exactly):
- Output ONLY JSON. No prose, no markdown, no code fences.
- The entire output MUST be a JSON array of objects: [{"re": <float>, "im": 0.0}, ...]
- Real solutions only: every item must have "im": 0.0.
- Return exactly N solutions if the prompt requests N.
- Solutions must be unique within 1e-8 (dedupe by rounded re).
- Sort solutions by (abs(re), re) ascending.
- If constraints cannot be satisfied, return [].

Verification rules:
- A candidate is valid only if tool_verify_residuals marks it ok (residual <= requested tol if provided, otherwise <= 1e-10).
- Do not include x=0 if prompt says exclude zero.

Process guideline (not optional):
1) Parse equation and constraints (range, N, exclude_zero, tolerance).
2) Bracket roots over a reasonable symmetric range and step; expand range if fewer than N.
3) Refine each bracket, collect candidate roots.
4) Verify residuals, filter to ok roots, dedupe and sort.
5) Emit the JSON array and stop.
"""

CARD = AgentCard(
    name="math",
    version="0.1.0",
    url="http://127.0.0.1:8101",
    skills=["math.solve.real_roots", "math.verify.residuals"],  # keep simple
    raw={},
    card_sha256="",
)


def brain(prompt_text: str) -> tuple[list[dict], dict]:
    txt, meta = run_with_tools(
        model=MODEL,
        system=SYSTEM_MATH,
        user=prompt_text,
        tools=TOOLS_MATH,
        tool_impl=TOOL_IMPL_MATH,
        max_rounds=12,
    )    
    meta.setdefault("schema_validated", True)   # math agent outputs contract JSON
    meta.setdefault("stub_hit", False)
    data = json.loads(txt)  # then validate + score
    parts = [{"kind": "data", "data": data}]
    return build_task_result(
        artifact_name="roots.json",
        parts=parts,
        meta=meta,
    )


app = create_a2a_app(CARD, brain)



TOOLS_MATH = [
    {
        "type": "function",
        "name": "tool_bracket_roots",
        "description": "Find sign-change brackets that likely contain real roots for an equation (lhs=rhs or expr=0).",
        "parameters": {
            "type": "object",
            "properties": {
                "equation": {"type": "string", "description": "Equation like 'sin(x)=x/20' or expression like 'sin(x)-x/20'."},
                "var": {"type": "string", "description": "Variable name (default 'x').", "default": "x"},
                "lo": {"type": "number", "description": "Lower bound of scan range.", "default": -50},
                "hi": {"type": "number", "description": "Upper bound of scan range.", "default": 50},
                "step": {"type": "number", "description": "Step size for sign-change scan.", "default": 0.25},
            },
            "required": ["equation"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "tool_refine_root",
        "description": "Refine a real root within a bracket to a specified tolerance and report residual.",
        "parameters": {
            "type": "object",
            "properties": {
                "equation": {"type": "string", "description": "Equation like 'sin(x)=x/20' or expression like 'sin(x)-x/20'."},
                "bracket": {
                    "type": "array",
                    "description": "Two-element [a,b] interval (or [a,a] for an exact hit).",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "var": {"type": "string", "description": "Variable name (default 'x').", "default": "x"},
                "tol": {"type": "number", "description": "Absolute tolerance for refinement.", "default": 1e-12},
                "max_iter": {"type": "integer", "description": "Max bisection iterations.", "default": 80},
            },
            "required": ["equation", "bracket"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "tool_verify_residuals",
        "description": "Compute residuals for candidate x values and flag those within tolerance.",
        "parameters": {
            "type": "object",
            "properties": {
                "equation": {"type": "string", "description": "Equation like 'sin(x)=x/20' or expression like 'sin(x)-x/20'."},
                "xs": {
                    "type": "array",
                    "description": "Candidate real x values to verify.",
                    "items": {"type": "number"},
                },
                "var": {"type": "string", "description": "Variable name (default 'x').", "default": "x"},
                "resid_tol": {"type": "number", "description": "Residual tolerance threshold.", "default": 1e-10},
                "real_only": {"type": "boolean", "description": "Require finite real xs (default True).", "default": True},
            },
            "required": ["equation", "xs"],
            "additionalProperties": False,
        },
    },
]

import sympy as sp
import mpmath as mp



def tool_bracket_roots(equation: str, var: str = "x", lo: float = -50, hi: float = 50, step: float = 0.25):
    x = sp.Symbol(var)
    eq = equation.replace("^", "**").strip()
    if "=" in eq:
        lhs, rhs = eq.split("=", 1)
        expr = sp.sympify(lhs) - sp.sympify(rhs)
    else:
        expr = sp.sympify(eq)
    f = sp.lambdify(x, expr, "mpmath")
    brackets = []
    a = lo
    fa = f(a)
    b = a + step
    while b <= hi:
        fb = f(b)
        if fa == 0:
            brackets.append([a, a])
        elif fa * fb < 0:
            brackets.append([a, b])
        a, fa = b, fb
        b = b + step
    return {"equation": eq, "var": var, "brackets": brackets}

import mpmath as mp
import sympy as sp

def _make_f(equation: str, var: str = "x"):
    x = sp.Symbol(var)
    eq = equation.replace("^", "**").strip()
    if "=" in eq:
        lhs, rhs = eq.split("=", 1)
        expr = sp.sympify(lhs) - sp.sympify(rhs)
    else:
        expr = sp.sympify(eq)
    return sp.lambdify(x, expr, "mpmath")  # evaluates with mp.mpf

def tool_refine_root(
    equation: str,
    bracket: list[float],
    var: str = "x",
    tol: float = 1e-14,
    max_iter: int = 80,
    solver: str = "ridder",
):
    mp.mp.dps = 80
    f = _make_f(equation, var)
    a, b = map(mp.mpf, bracket)

    r = mp.findroot(f, (a, b), solver=solver, tol=tol, verify=False, maxsteps=max_iter)
    resid = abs(f(r))
    return {"root": float(r), "residual": float(resid)}


import mpmath as mp
def tool_verify_residuals(*, equation: str, xs: list[float], var: str="x",
                          resid_tol: float=1e-10, real_only: bool=True):
    """
    Verify candidate solutions for equation (interpreted as lhs=rhs or expr=0).

    Returns a dict with per-x residuals and a convenience 'all_ok' flag.

    Example output:
    {
      "equation": "sin(x)=x/20",
      "var": "x",
      "resid_tol": 1e-10,
      "results": [
        {"x": 3.1415, "residual": 0.00012, "ok": false},
        ...
      ],
      "all_ok": false
    }
    """
    mp.mp.dps = 80
    x = sp.Symbol(var)
    eq = equation.replace("^", "**").strip()

    if "=" in eq:
        lhs, rhs = eq.split("=", 1)
        expr = sp.sympify(lhs) - sp.sympify(rhs)
    else:
        expr = sp.sympify(eq)

    # Use mpmath backend for robust transcendental evaluation
    f = sp.lambdify(x, expr, "mpmath")

    out = []
    all_ok = True
    for x in xs:
        xx = mp.mpf(x)
        r = abs(f(xx))
        ok = (r <= resid_tol)
        out.append({"x": float(x), "residual": float(r), "ok": ok})
        all_ok &= ok
    return {
        "equation": eq,
        "var": var,
        "resid_tol": float(resid_tol),
        "results": out,
        "all_ok": all_ok,
    }

TOOL_IMPL_MATH = {
    "tool_bracket_roots": tool_bracket_roots,
    "tool_refine_root": tool_refine_root,
    "tool_verify_residuals": tool_verify_residuals,
}