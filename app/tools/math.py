from __future__ import annotations

import ast
import operator
from typing import Any

from app.tools.base import Tool


_ALLOWED_OPERATORS: dict[type[ast.AST], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    raise ValueError("Unsupported expression")


class MathTool(Tool):
    """Evaluates arithmetic expressions with strict validation."""

    name = "math"
    description = "Safely evaluates arithmetic expressions (+, -, *, /, **, %)."
    input_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "Arithmetic expression"}},
        "required": ["expression"],
    }

    async def run(self, expression: str) -> dict:
        if not expression or not isinstance(expression, str):
            raise ValueError("Expression must be a string")

        try:
            parsed = ast.parse(expression, mode="eval")
            value = _safe_eval(parsed)
        except SyntaxError as exc:
            raise ValueError(f"Invalid syntax: {exc.msg}") from exc

        return {
            "success": True,
            "data": {
                "result": value,
                "expression": expression
            },
            "message": f"Calculated {expression} = {value}"
        }

