"""Community Plugin Skill: Deep Focus Pomodoro Panel returning a Generative UI."""

from __future__ import annotations

SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "focus_session",
        "description": "Cria um painel visual de foco profundo (Pomodoro) com metas clicáveis.",
        "parameters": {
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Duração em minutos (padrão 25)"},
                "goal": {"type": "string", "description": "Meta principal da sessão"},
            },
            "required": ["goal"],
        },
    },
}

KEYWORDS = ["foco", "pomodoro", "concentrar"]


def run(args: dict) -> str:
    mins = int(args.get("minutes") or 25)
    goal = str(args.get("goal") or "Foco profundo no projeto")[:46]
    spec = "\n".join([
        f"KPI|Ciclo|{mins} min|cyan",
        "KPI|Pausa|5 min|indigo",
        "KPI|Modo|Zero Distrações|green",
        f"TXT|Meta atual: {goal}",
        "CHK|0|Silenciar notificações externas no Guardian",
        "CHK|0|Concluir bloco principal sem alternar contexto",
        "CHK|0|Registrar progresso no SemanticFS ao finalizar",
    ])
    return f"UI|plugin:pomodoro|Sessão de Foco Profundo|{spec}"
