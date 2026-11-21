"""Planning, Itinerary & Checklist Capability Engine."""

from __future__ import annotations

from ...models import CapabilityManifest, CapabilityPermission, WorkspaceBlock
from ..base import CapabilityContext, CapabilityEngine


class PlannerEngine(CapabilityEngine):
    manifest = CapabilityManifest(
        id="planner_engine",
        name="Motor de Planejamento & Fluxos",
        version="0.1.0",
        description="Cronogramas dinâmicos, roteiros por dia e checklists reativos.",
        intents=["travel_planning", "project_planning", "general_workspace"],
        keywords=["planejar", "roteiro", "cronograma", "checklist", "tarefas", "projeto", "etapas"],
        permissions=CapabilityPermission(network=False, vault="none", semantic_fs="read"),
        source="builtin",
    )

    async def execute(self, ctx: CapabilityContext) -> list[WorkspaceBlock]:
        days = int(ctx.params.get("days", 5))
        destination = str(ctx.params.get("destination", "Destino"))

        if ctx.intent_type == "travel_planning":
            items = [
                {
                    "id": f"t{i}",
                    "day": f"Dia {i}",
                    "title": (
                        f"Chegada em {destination} e check-in" if i == 1
                        else f"Despedida, compras locais e retorno" if i == days
                        else f"Exploração cultural e gastronomia local (Parte {i - 1})"
                    ),
                    "done": False,
                }
                for i in range(1, max(days, 1) + 1)
            ]
            return [
                WorkspaceBlock(
                    id="blk_itinerary",
                    type="checklist_timeline",
                    title=f"Roteiro Dinâmico ({days} dias)",
                    capability=self.manifest.id,
                    col_span=12,
                    accepts_drop=["note", "document"],
                    data={"items": items},
                )
            ]

        items = [
            {"id": "t1", "day": "Etapa 1", "title": "Definir escopo e critérios de sucesso", "done": False},
            {"id": "t2", "day": "Etapa 2", "title": "Reunir referências do SemanticFS", "done": False},
            {"id": "t3", "day": "Etapa 3", "title": "Executar e validar entrega", "done": False},
            {"id": "t4", "day": "Etapa 4", "title": "Revisar e dissolver contexto no grafo", "done": False},
        ]
        return [
            WorkspaceBlock(
                id="blk_tasks",
                type="checklist_timeline",
                title="Fluxo de Ações & Cronograma",
                capability=self.manifest.id,
                col_span=4,
                accepts_drop=["note", "document"],
                data={"items": items},
            )
        ]
