"""Community Plugin Skill: Safe Math Calculator returning a Generative UI Card."""

from __future__ import annotations

import ast
import operator

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "calculate_expression",
        "description": "Calcula expressões matemáticas com precisão (ex: '4000 / 5', '1250 * 1.15').",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Expressão matemática"},
            },
            "required": ["expression"],
        },
    },
}

KEYWORDS = ["calcule ", "calcular ", "quanto e ", "quanto é "]


def _safe_eval(expr: str) -> float:
    clean = expr.replace(",", ".").replace("x", "*").replace("×", "*").strip()
    node = ast.parse(clean, mode="eval").body

    def _ev(n: ast.AST) -> float:
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return float(_OPS[type(n.op)](_ev(n.left), _ev(n.right)))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return float(_OPS[type(n.op)](_ev(n.operand)))
        raise ValueError("Operação não permitida")

    return round(_ev(node), 4)


def run(args: dict) -> str:
    expr = str(args.get("expression") or "0")
    try:
        val = _safe_eval(expr)
        spec = "\n".join([
            f"KPI|Expressão|{expr[:22]}|cyan",
            f"KPI|Resultado|{val}|green",
            "KPI|Execução|Plugin Local|indigo",
            "TXT|Cálculo executado pelo plugin auto-descoberto skills/calculator.py (AST seguro).",
        ])
        return f"UI|plugin:calculator|Calculadora Newera|{spec}"
    except Exception as exc:
        return f"RESP|plugin:calculator|Erro de Cálculo|Não foi possível calcular '{expr}': {exc}"
