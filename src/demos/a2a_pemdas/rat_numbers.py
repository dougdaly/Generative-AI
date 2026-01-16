from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict

# Functions for representing numbers as rationals (n/d)
RatObj = Dict[str, Any]

def to_wire(x: Any) -> Any:
    """
    Recursively convert Python objects into JSON-safe wire format.
    - Fraction -> rat object
    - dict/list/tuple -> recurse
    - everything else -> unchanged (must already be JSON-serializable)
    """
    if isinstance(x, Fraction):
        return frac_to_rat(x)
    if isinstance(x, dict):
        return {k: to_wire(v) for k, v in x.items()}
    if isinstance(x, list):
        return [to_wire(v) for v in x]
    if isinstance(x, tuple):
        return [to_wire(v) for v in x]  # tuples become JSON arrays
    return x


def rat_to_frac(obj: RatObj) -> Fraction:
    """Convert {"type":"rat:v1","n":<int>,"d":<int>} -> Fraction (auto-reduced)."""
    if not isinstance(obj, dict):
        raise TypeError(f"rat_to_frac expected dict, got {type(obj).__name__}")

    if obj.get("type") != "rat:v1":
        raise ValueError(f"Expected type='rat:v1', got {obj.get('type')!r}")

    if "n" not in obj or "d" not in obj:
        raise ValueError("rat:v1 requires fields 'n' and 'd'")

    n = int(obj["n"])
    d = int(obj["d"])
    if d == 0:
        raise ValueError("rat:v1 denominator 'd' cannot be 0")

    return Fraction(n, d)  # reduced; denominator positive


def frac_to_rat(x: Fraction) -> RatObj:
    """Convert Fraction -> {"type":"rat:v1","n":...,"d":...} (already reduced)."""
    if not isinstance(x, Fraction):
        raise TypeError(f"frac_to_rat expected Fraction, got {type(x).__name__}")

    return {"type": "rat:v1", "n": x.numerator, "d": x.denominator}


def int_to_rat(n: int) -> RatObj:
    """Convert int -> rat:v1 object."""
    return {"type": "rat:v1", "n": int(n), "d": 1}


def recip_rat(obj: RatObj) -> RatObj:
    """Reciprocal of rat:v1 object. Rejects zero numerator."""
    f = rat_to_frac(obj)
    if f.numerator == 0:
        raise ValueError("Cannot take reciprocal of 0")
    return frac_to_rat(1 / f)


def fmt_frac(x: Fraction) -> str:
    """Human-friendly string for traces."""
    if x.denominator == 1:
        return str(x.numerator)
    return f"{x.numerator}/{x.denominator}"
