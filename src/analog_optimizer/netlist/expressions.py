"""Whitelist arithmetic evaluator. Never execute source expressions."""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Callable


SCALES = {"T": 1e12, "G": 1e9, "M": 1e6, "K": 1e3, "k": 1e3,
          "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18}
NUMBER = re.compile(r"(?<![\w.])((?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z]+)?")


class UnresolvedExpression(ValueError):
    pass


def evaluate(raw: str, lookup: Callable[[str], float]) -> float:
    expression = raw.strip()
    if len(expression) > 4096:
        raise UnresolvedExpression("Expression exceeds length limit")
    if expression[:1] in ("'", '"', "{"):
        close = {"'": "'", '"': '"', "{": "}"}[expression[0]]
        if not expression.endswith(close):
            raise UnresolvedExpression("Unclosed expression")
        expression = expression[1:-1]

    def number(match: re.Match) -> str:
        suffix = match[2]
        if suffix and suffix not in SCALES:
            raise UnresolvedExpression(f"Unsupported numeric suffix {suffix!r}")
        value = float(match[1]) * SCALES.get(suffix, 1.0)
        if not math.isfinite(value):
            raise UnresolvedExpression("Non-finite numeric literal")
        return repr(value)

    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Pow: operator.pow}

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name):
            return lookup(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise UnresolvedExpression("Exponent exceeds limit")
            return binary[type(node.op)](left, right)
        raise UnresolvedExpression(f"Unsupported expression node {type(node).__name__}")

    try:
        tree = ast.parse(NUMBER.sub(number, expression), mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 128:
            raise UnresolvedExpression("Expression exceeds complexity limit")
        value = float(visit(tree.body))
        if not math.isfinite(value):
            raise UnresolvedExpression("Non-finite value")
        return value
    except (SyntaxError, ValueError, TypeError, ArithmeticError, RecursionError) as exc:
        raise UnresolvedExpression(str(exc)) from exc
