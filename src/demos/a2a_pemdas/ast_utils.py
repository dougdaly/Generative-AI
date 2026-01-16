from __future__ import annotations

import ast
from dataclasses import dataclass
from fractions import Fraction
from typing import Any


@dataclass(frozen=True)
class Num:
    v: Fraction
    def __post_init__(self):
        if not isinstance(self.v, Fraction):
            raise TypeError(f"Num.v must be Fraction, got {type(self.v).__name__}: {self.v!r}")

@dataclass(frozen=True)
class Bin:
    op: str  # "+", "-", "*", "/"
    left: Any
    right: Any


def _ast_to_node(node: ast.AST) -> Any:
    # Strict v2: integer literals only
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int):
            return Num(Fraction(node.value, 1))
        if isinstance(node.value, float):
            raise ValueError("Float literals not allowed in v2 (use rationals via division, e.g. 1/10)")
        raise ValueError(f"Unsupported literal: {node.value!r}")

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _ast_to_node(node.operand)
        if not isinstance(inner, Num):
            raise ValueError("Unary +/- only supported on integer literals in v2")
        return inner if isinstance(node.op, ast.UAdd) else Num(-inner.v)

    if isinstance(node, ast.BinOp):
        left = _ast_to_node(node.left)
        right = _ast_to_node(node.right)

        if isinstance(node.op, ast.Add):  return Bin("+", left, right)
        if isinstance(node.op, ast.Sub):  return Bin("-", left, right)
        if isinstance(node.op, ast.Mult): return Bin("*", left, right)
        if isinstance(node.op, ast.Div):  return Bin("/", left, right)

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def parse_expression(expr: str) -> Any:
    tree = ast.parse(expr, mode="eval")
    return _ast_to_node(tree.body)


def is_reducible(node: Any) -> bool:
    return isinstance(node, Bin) and isinstance(node.left, Num) and isinstance(node.right, Num)


def render_debug(node: Any) -> str:
    """Fully parenthesized; great for traces."""
    if isinstance(node, Num):
        return _fmt_frac(node.v)
    if isinstance(node, Bin):
        return f"({render_debug(node.left)}{node.op}{render_debug(node.right)})"
    raise TypeError("Unknown node type")


_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}


def render_pretty(node: Any, parent_prec: int = 0, is_right: bool = False) -> str:
    """Precedence-aware rendering with minimal parentheses."""
    if isinstance(node, Num):
        return _fmt_frac(node.v)

    if not isinstance(node, Bin):
        raise TypeError("Unknown node type")

    prec = _PRECEDENCE[node.op]

    left_s = render_pretty(node.left, prec, is_right=False)
    right_s = render_pretty(node.right, prec, is_right=True)

    s = f"{left_s}{node.op}{right_s}"

    need_parens = prec < parent_prec
    if is_right and prec == parent_prec and node.op in ("-", "/"):
        need_parens = True

    return f"({s})" if need_parens else s


def _fmt_frac(x: Fraction) -> str:
    if not isinstance(x, Fraction):
        raise TypeError(f"_fmt_frac expected Fraction, got {type(x).__name__}: {x!r}")
    if x.denominator == 1:
        return str(x.numerator)
    return f"{x.numerator}/{x.denominator}"
