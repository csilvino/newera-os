"""Calculation & Dynamic Budget Capability Engine (safe AST evaluator + reactive sheets)."""

from __future__ import annotations

import ast
import operator
from typing import Any

from ...models import CapabilityManifest, CapabilityPermission, WorkspaceBlock
from ..base import CapabilityContext, CapabilityEngine

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_math(expression: str) -> float | None:
    """Safely evaluates arithmetic expressions using Python AST (no eval)."""
    try:
        clean = expression.replace(",", ".").replace("x", "*").replace("×", "*").strip()
        node = ast.parse(clean, mode="eval").body

        def _eval(n: ast.AST) -> float:
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return float(n.value)
            if isinstance(n, ast.BinOp) and type(n.op) in _SAFE_OPS:
                left = _eval(n.left)
                right = _eval(n.right)
                if isinstance(n.op, ast.Pow) and abs(right) > 12:
                    raise ValueError("Exponent too large")
                return float(_SAFE_OPS[type(n.op)](left, right))
            if isinstance(n, ast.UnaryOp) and type(n.op) in _SAFE_OPS:
                return float(_SAFE_OPS[type(n.op)](_eval(n.operand)))
            raise ValueError("Unsupported syntax")

        return round(_eval(node), 4)
    except Exception:
        return None


def compute_budget_summary(rows: list[dict[str, Any]], budget_limit: float) -> dict[str, Any]:
    total = round(sum(float(r.get("cost", 0) or 0) * float(r.get("qty", 1) or 1) for r in rows), 2)
    remaining = round(budget_limit - total, 2)
    pct = round((total / budget_limit) * 100, 1) if budget_limit > 0 else 0.0
    by_category: dict[str, float] = {}
    for r in rows:
        cat = str(r.get("category") or "Geral")
        by_category[cat] = round(by_category.get(cat, 0.0) + float(r.get("cost", 0) or 0) * float(r.get("qty", 1) or 1), 2)
    return {
        "total": total,
        "budget_limit": budget_limit,
        "remaining": remaining,
        "utilization_pct": pct,
        "status": "ok" if remaining >= 0 else "alert",
        "chart": [{"category": k, "amount": v} for k, v in by_category.items()],
    }


class CalcEngine(CapabilityEngine):
    manifest = CapabilityManifest(
        id="calc_engine",
        name="Motor de Cálculo & Orçamento",
        version="0.1.0",
        description="Planilhas dinâmicas reativas, orçamento inteligente e avaliação matemática segura.",
        intents=["travel_planning", "finance_budget", "calculation"],
        keywords=["orçamento", "orcamento", "custo", "planilha", "calcular", "gasto", "finanças"],
        permissions=CapabilityPermission(network=False, vault="none", semantic_fs="read"),
        source="builtin",
    )

    async def execute(self, ctx: CapabilityContext) -> list[WorkspaceBlock]:
        budget = float(ctx.params.get("budget", 4000.0))
        days = int(ctx.params.get("days", 5))
        destination = str(ctx.params.get("destination", "Destino"))

        if ctx.intent_type == "travel_planning":
            # Balanced realistic travel budget allocation
            lodging_per_night = round((budget * 0.36) / max(days, 1), 2)
            food_per_day = round((budget * 0.22) / max(days, 1), 2)
            transport = round(budget * 0.24, 2)
            tours = round(budget * 0.12, 2)
            reserve = round(budget * 0.06, 2)

            rows = [
                {"id": "r1", "category": "Transporte", "item": f"Passagens / deslocamento ({destination})", "qty": 1, "cost": transport},
                {"id": "r2", "category": "Hospedagem", "item": f"Hospedagem ({days} diárias)", "qty": days, "cost": lodging_per_night},
                {"id": "r3", "category": "Alimentação", "item": f"Refeições ({days} dias)", "qty": days, "cost": food_per_day},
                {"id": "r4", "category": "Experiências", "item": "Passeios e ingressos", "qty": 1, "cost": tours},
                {"id": "r5", "category": "Reserva", "item": "Margem de segurança", "qty": 1, "cost": reserve},
            ]
        elif ctx.intent_type == "calculation" and ctx.params.get("expression"):
            expr = str(ctx.params["expression"])
            val = safe_eval_math(expr)
            rows = [
                {"id": "r1", "category": "Cálculo", "item": f"Expressão: {expr}", "qty": 1, "cost": val or 0.0}
            ]
            budget = max(abs(val or 0.0), 1000.0)
        else:
            rows = [
                {"id": "r1", "category": "Essencial", "item": "Custos fixos principais", "qty": 1, "cost": round(budget * 0.45, 2)},
                {"id": "r2", "category": "Operacional", "item": "Serviços e ferramentas", "qty": 1, "cost": round(budget * 0.25, 2)},
                {"id": "r3", "category": "Investimento", "item": "Reserva / crescimento", "qty": 1, "cost": round(budget * 0.20, 2)},
            ]

        summary = compute_budget_summary(rows, budget)
        return [
            WorkspaceBlock(
                id="blk_budget",
                type="budget_sheet",
                title="Planilha Dinâmica de Custos",
                capability=self.manifest.id,
                col_span=7,
                accepts_drop=["document", "dataset", "note"],
                data={
                    "currency": "BRL",
                    "budget_limit": budget,
                    "rows": rows,
                    "summary": summary,
                },
            )
        ]
