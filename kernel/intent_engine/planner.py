"""Intent Engine — Classifies human intent, composes reactive WorkspaceGraphs, and executes Intent Physics."""

from __future__ import annotations

import copy
import re
import time
import uuid
from typing import Any

from ..capabilities.base import CapabilityContext, CapabilityRegistry
from ..capabilities.builtin.calc_engine import compute_budget_summary
from ..guardian.service import GuardianService
from ..models import (
    DataWire,
    EssenceMetric,
    ExecutionTraceStep,
    IntentRequest,
    WorkspaceBlock,
    WorkspaceEssence,
    WorkspaceGraph,
    WorkspaceSnapshot,
    utc_now_iso,
)
from ..semantic_fs.extractor import extract_numeric_items
from ..semantic_fs.store import SemanticFS
from ..semantic_fs.vectorizer import normalize_text
from .llm_bridge import LLMBridge

_BUDGET_RE = re.compile(r"(?:r\$\s?|or[cç]amento\s+(?:de\s+)?(?:r\$\s?)?)([\d\.,]+)", re.IGNORECASE)
_DAYS_RE = re.compile(r"(\d+)\s*(?:dias?|di[aá]rias?)", re.IGNORECASE)
_MINUTES_RE = re.compile(r"(\d+)\s*(?:min(?:utos?)?)", re.IGNORECASE)
_DEST_RE = re.compile(
    r"(?:para|pra|em|destino)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+(?:de|do|da|dos|das)?\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ]?[a-záéíóúâêôãõç]+){0,2})"
)
_MATH_RE = re.compile(r"^\s*(?:calcule|calcular|quanto\s+[eé])?\s*([\d\.,\s\+\-\*/\(\)×x]+)\s*\??$", re.IGNORECASE)


def _parse_brl_number(raw: str) -> float:
    cleaned = raw.strip()
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # e.g. 4.000 -> 4000
        parts = cleaned.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            cleaned = "".join(parts)
    try:
        return float(cleaned)
    except ValueError:
        return 4000.0


def _format_brl(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


class IntentEngine:
    """Core orchestrator turning natural-language intentions into live ephemeral workspaces."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        semantic_fs: SemanticFS,
        guardian: GuardianService,
        llm_bridge: LLMBridge,
    ) -> None:
        self.registry = registry
        self.semantic_fs = semantic_fs
        self.guardian = guardian
        self.llm_bridge = llm_bridge

    def _classify_and_extract(self, query: str) -> tuple[str, dict[str, Any]]:
        norm = normalize_text(query)
        params: dict[str, Any] = {}

        # Extract numeric parameters
        b_match = _BUDGET_RE.search(query)
        if b_match:
            params["budget"] = _parse_brl_number(b_match.group(1))
        d_match = _DAYS_RE.search(query)
        if d_match:
            params["days"] = max(1, min(int(d_match.group(1)), 30))
        m_match = _MINUTES_RE.search(query)
        if m_match:
            params["minutes"] = max(5, min(int(m_match.group(1)), 120))
        dest_match = _DEST_RE.search(query)
        if dest_match:
            candidate = dest_match.group(1).strip()
            if normalize_text(candidate) not in {"o", "a", "os", "as", "um", "uma", "semana"}:
                params["destination"] = candidate

        # Pure math check
        math_match = _MATH_RE.match(query)
        if math_match and any(op in math_match.group(1) for op in ("+", "-", "*", "/", "x", "×")):
            params["expression"] = math_match.group(1).strip()
            return "calculation", params

        # Community contrib capability match
        if self.registry.match_contrib_by_query(norm):
            return "focus_session", params

        # Travel planning
        if any(k in norm for k in ("viagem", "viajar", "roteiro", "ferias", "turismo", "hotel")):
            params.setdefault("days", 5)
            params.setdefault("budget", 4000.0)
            params.setdefault("destination", "Florianópolis")
            return "travel_planning", params

        # Semantic recall (folderless search)
        if any(k in norm for k in ("mostre", "mostrar", "procure", "ache", "contrato", "pdf", "revisei", "semana passada", "arquivo", "documento", "lembra")):
            return "semantic_recall", params

        # Finance / budget
        if any(k in norm for k in ("orcamento", "planilha", "custo", "gasto", "financas", "despesa", "fatura")):
            params.setdefault("budget", 5000.0)
            return "finance_budget", params

        # Project planning
        if any(k in norm for k in ("planejar", "projeto", "cronograma", "checklist", "tarefas", "estrategia")):
            return "project_planning", params

        return "general_workspace", params

    async def plan_workspace(self, request: IntentRequest) -> WorkspaceGraph:
        trace: list[ExecutionTraceStep] = []

        # Step 1: Guardian local PII inspection
        t0 = time.perf_counter()
        pii_check = self.guardian.sanitize_outbound(request.query, target="intent_engine:local")
        trace.append(
            ExecutionTraceStep(
                step="1. Guardian Privacy Check",
                component="guardian.pii_proxy",
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                detail=f"Inspeção local concluída ({pii_check['redacted_count']} itens sensíveis detectados).",
                privacy_checked=True,
            )
        )

        # Step 2: Intent classification & parameter extraction
        t1 = time.perf_counter()
        intent_type, params = self._classify_and_extract(request.query)
        trace.append(
            ExecutionTraceStep(
                step="2. Intent Classification",
                component="intent_engine.classifier",
                duration_ms=round((time.perf_counter() - t1) * 1000, 2),
                detail=f"Intenção='{intent_type}' · Parâmetros={params}",
            )
        )

        # Step 3: SemanticFS contextual recall
        t2 = time.perf_counter()
        semantic_hits = self.semantic_fs.search(request.query, limit=6)
        trace.append(
            ExecutionTraceStep(
                step="3. SemanticFS Context Recall",
                component="semantic_fs.hybrid_search",
                duration_ms=round((time.perf_counter() - t2) * 1000, 2),
                detail=f"{len(semantic_hits)} memória(s) semântica(s) recuperadas sem pastas.",
            )
        )

        # Step 4: Select & execute capability engines
        ctx = CapabilityContext(
            query=request.query,
            intent_type=intent_type,
            params=params,
            semantic_hits=semantic_hits,
            device_type=request.device_type,
        )

        engines = self._select_engines(intent_type, request.query)
        blocks: list[WorkspaceBlock] = []
        for eng in engines:
            te = time.perf_counter()
            produced = await eng.execute(ctx)
            blocks.extend(produced)
            trace.append(
                ExecutionTraceStep(
                    step=f"4. Capability [{eng.manifest.id}]",
                    component=f"capabilities.{eng.manifest.source}.{eng.manifest.id}",
                    duration_ms=round((time.perf_counter() - te) * 1000, 2),
                    detail=f"Gerou {len(produced)} bloco(s) · Permissões: net={eng.manifest.permissions.network}, fs={eng.manifest.permissions.semantic_fs}",
                )
            )

        # Step 5: Optional LLM headline enrichment (guarded)
        llm_info = await self.llm_bridge.enrich_headline(request.query, intent_type)
        if llm_info["used_llm"]:
            trace.append(
                ExecutionTraceStep(
                    step="5. Optional LLM Enrichment",
                    component=f"llm_bridge.{llm_info['provider']}",
                    duration_ms=0.0,
                    detail=f"Enriquecimento protegido pelo Guardian ({llm_info['pii_redacted']} PII mascarados).",
                )
            )

        wires = self._build_wires(blocks)
        essence = self._compute_essence(intent_type, request.query, blocks, params, llm_info.get("text"))
        title = self._build_title(intent_type, request.query, params, semantic_hits)

        ws_id = f"ws_{uuid.uuid4().hex[:10]}"
        initial_snapshot = WorkspaceSnapshot(
            version=1,
            summary=f"Workspace criado a partir da intenção: {request.query[:80]}",
            blocks=copy.deepcopy(blocks),
            essence=copy.deepcopy(essence),
        )

        return WorkspaceGraph(
            id=ws_id,
            title=title,
            intent_query=request.query,
            intent_type=intent_type,
            status="active",
            version=1,
            essence=essence,
            blocks=blocks,
            wires=wires,
            semantic_sources=[
                {
                    "id": h.id,
                    "title": h.title,
                    "kind": h.kind,
                    "score": h.score,
                    "tags": h.tags,
                }
                for h in semantic_hits[:5]
            ],
            trace=trace,
            history=[initial_snapshot],
        )

    def _select_engines(self, intent_type: str, query: str) -> list[Any]:
        norm = normalize_text(query)
        order_map: dict[str, list[str]] = {
            "travel_planning": ["calc_engine", "geo_weather_engine", "planner_engine"],
            "finance_budget": ["calc_engine", "docs_engine"],
            "calculation": ["calc_engine"],
            "semantic_recall": ["docs_engine"],
            "project_planning": ["docs_engine", "planner_engine"],
            "general_workspace": ["docs_engine", "planner_engine"],
        }
        selected = []
        if intent_type == "focus_session":
            selected.extend(self.registry.match_contrib_by_query(norm))
            planner = self.registry.get("planner_engine")
            if planner:
                selected.append(planner)
            return selected

        for cap_id in order_map.get(intent_type, ["docs_engine"]):
            eng = self.registry.get(cap_id)
            if eng:
                selected.append(eng)
        return selected

    def _build_wires(self, blocks: list[WorkspaceBlock]) -> list[DataWire]:
        block_ids = {b.id for b in blocks}
        wires: list[DataWire] = []
        if "blk_budget" in block_ids:
            wires.append(
                DataWire(
                    id="wire_budget_essence",
                    from_block="blk_budget",
                    from_field="summary.total",
                    to_block="essence",
                    to_field="metrics.saldo",
                    label="Recalcula saldo e alerta de orçamento em tempo real",
                )
            )
        if "blk_budget" in block_ids and "blk_itinerary" in block_ids:
            wires.append(
                DataWire(
                    id="wire_budget_itinerary",
                    from_block="blk_itinerary",
                    from_field="items.length",
                    to_block="blk_budget",
                    to_field="rows.hospedagem",
                    label="Sincroniza dias do roteiro com diárias da planilha",
                )
            )
        if "blk_map_weather" in block_ids and "blk_itinerary" in block_ids:
            wires.append(
                DataWire(
                    id="wire_weather_itinerary",
                    from_block="blk_map_weather",
                    from_field="forecast",
                    to_block="blk_itinerary",
                    to_field="day_conditions",
                    label="Informa previsão do tempo para cada dia do roteiro",
                )
            )
        if "blk_semantic_doc" in block_ids and "blk_notes" in block_ids:
            wires.append(
                DataWire(
                    id="wire_semantic_notes",
                    from_block="blk_semantic_doc",
                    from_field="entities",
                    to_block="blk_notes",
                    to_field="context_header",
                    label="Vincula entidades do documento às notas da revisão",
                )
            )
        return wires

    def _build_title(
        self,
        intent_type: str,
        query: str,
        params: dict[str, Any],
        semantic_hits: list[Any],
    ) -> str:
        if intent_type == "travel_planning":
            dest = params.get("destination", "Destino")
            days = params.get("days", 5)
            return f"Viagem — {dest} ({days} dias)"
        if intent_type == "semantic_recall" and semantic_hits:
            return f"Memória — {semantic_hits[0].title}"
        if intent_type == "finance_budget":
            return f"Orçamento Dinâmico ({_format_brl(float(params.get('budget', 5000)))})"
        if intent_type == "focus_session":
            return "Sessão de Foco Profundo"
        if intent_type == "calculation":
            return f"Cálculo — {params.get('expression', query[:30])}"
        return query.strip().capitalize()[:60]

    def _compute_essence(
        self,
        intent_type: str,
        query: str,
        blocks: list[WorkspaceBlock],
        params: dict[str, Any],
        llm_headline: str | None = None,
    ) -> WorkspaceEssence:
        metrics: list[EssenceMetric] = []
        next_actions: list[str] = []
        headline = llm_headline or f"Espaço gerado para: {query[:90]}"
        subheadline = "Interface efêmera ativa — edite os blocos ou refine pela barra de intenção."

        for blk in blocks:
            if blk.type == "budget_sheet":
                s = blk.data.get("summary", {})
                rem = float(s.get("remaining", 0))
                total = float(s.get("total", 0))
                limit_v = float(s.get("budget_limit", 0))
                status = "ok" if rem >= 0 else "alert"
                metrics.append(EssenceMetric(label="Total Previsto", value=_format_brl(total), status="info"))
                metrics.append(
                    EssenceMetric(
                        label="Saldo" if rem >= 0 else "Acima do Teto",
                        value=_format_brl(abs(rem)),
                        status=status,  # type: ignore[arg-type]
                    )
                )
                if intent_type == "travel_planning" and not llm_headline:
                    headline = (
                        f"Roteiro para {params.get('destination', 'o destino')} dentro do orçamento de {_format_brl(limit_v)}"
                        if rem >= 0
                        else f"Atenção: custos excedem o orçamento em {_format_brl(abs(rem))}"
                    )
                next_actions.append("Ajustar valores na planilha ou arrastar uma fatura do SemanticFS")

            elif blk.type == "map_weather":
                forecast = blk.data.get("forecast") or []
                if forecast:
                    first = forecast[0]
                    metrics.append(
                        EssenceMetric(
                            label="Clima Previsto",
                            value=f"{first.get('temp_max')}°C · {first.get('condition')}",
                            status="ok",
                        )
                    )
            elif blk.type == "checklist_timeline":
                items = blk.data.get("items") or []
                done = sum(1 for i in items if i.get("done"))
                metrics.append(
                    EssenceMetric(
                        label="Progresso",
                        value=f"{done}/{len(items)} etapas",
                        status="ok" if done == len(items) and items else "info",
                    )
                )
            elif blk.type == "semantic_viewer":
                score = blk.data.get("score")
                metrics.append(
                    EssenceMetric(
                        label="Relevância Semântica",
                        value=f"{int(round((score or 0.85) * 100))}%",
                        status="ok",
                    )
                )
                if not llm_headline:
                    headline = f"Documento localizado sem pastas: {blk.data.get('title')}"
                next_actions.append("Revisar conteúdo ou emitir token seguro pelo Guardian")
            elif blk.type == "focus_timer":
                metrics.append(
                    EssenceMetric(
                        label="Ciclo de Foco",
                        value=f"{blk.data.get('duration_minutes', 25)} min",
                        status="ok",
                    )
                )

        if not next_actions:
            next_actions = ["Refinar interface por voz ou texto", "Concluir e dissolver no grafo semântico"]

        return WorkspaceEssence(
            headline=headline,
            subheadline=subheadline,
            metrics=metrics,
            next_actions=next_actions,
        )

    def recompute_workspace(self, ws: WorkspaceGraph, summary_note: str = "Atualização reativa") -> WorkspaceGraph:
        """Recomputes reactive fields (like budget totals + essence) and records a Time-Travel snapshot."""
        for blk in ws.blocks:
            if blk.type == "budget_sheet":
                rows = blk.data.get("rows", [])
                limit_v = float(blk.data.get("budget_limit", 4000))
                blk.data["summary"] = compute_budget_summary(rows, limit_v)

        ws.essence = self._compute_essence(ws.intent_type, ws.intent_query, ws.blocks, {})
        ws.version += 1
        ws.updated_at = utc_now_iso()
        ws.history.append(
            WorkspaceSnapshot(
                version=ws.version,
                summary=summary_note,
                blocks=copy.deepcopy(ws.blocks),
                essence=copy.deepcopy(ws.essence),
            )
        )
        # Keep last 25 snapshots in working memory
        if len(ws.history) > 25:
            ws.history = ws.history[-25:]
        return ws

    async def refine_workspace(self, ws: WorkspaceGraph, command: str) -> WorkspaceGraph:
        """Mutates an active ephemeral workspace from natural language without restarting."""
        norm = normalize_text(command)

        # Budget adjustment command (e.g. "reduza o orçamento para R$ 3.200")
        b_match = _BUDGET_RE.search(command)
        if b_match and any(b.type == "budget_sheet" for b in ws.blocks):
            new_budget = _parse_brl_number(b_match.group(1))
            for blk in ws.blocks:
                if blk.type == "budget_sheet":
                    blk.data["budget_limit"] = new_budget
            return self.recompute_workspace(ws, f"Orçamento ajustado para {_format_brl(new_budget)}")

        # Add checklist/block command
        if "checklist" in norm or "mala" in norm or "lista" in norm:
            ws.blocks.append(
                WorkspaceBlock(
                    id=f"blk_extra_{uuid.uuid4().hex[:6]}",
                    type="checklist_timeline",
                    title=f"Checklist — {command.strip().capitalize()[:40]}",
                    capability="planner_engine",
                    col_span=6,
                    data={
                        "items": [
                            {"id": "c1", "day": "Item 1", "title": "Documentos e identidade", "done": False},
                            {"id": "c2", "day": "Item 2", "title": "Carregadores e adaptadores", "done": False},
                            {"id": "c3", "day": "Item 3", "title": "Roupas adequadas ao clima previsto", "done": False},
                        ]
                    },
                )
            )
            return self.recompute_workspace(ws, f"Bloco adicionado: {command[:50]}")

        # Add notes/doc block
        if "nota" in norm or "resumo" in norm or "documento" in norm:
            ws.blocks.append(
                WorkspaceBlock(
                    id=f"blk_note_{uuid.uuid4().hex[:6]}",
                    type="doc_editor",
                    title="Bloco de Notas Adicionado",
                    capability="docs_engine",
                    col_span=6,
                    accepts_drop=["document", "note", "dataset"],
                    data={"markdown": f"## {command.strip().capitalize()}\n\n- "},
                )
            )
            return self.recompute_workspace(ws, f"Editor adicionado: {command[:50]}")

        # Add focus timer (contrib)
        if "foco" in norm or "pomodoro" in norm:
            eng = self.registry.get("focus_pomodoro")
            if eng:
                added = await eng.execute(CapabilityContext(query=command, intent_type="focus_session"))
                ws.blocks.extend(added)
                return self.recompute_workspace(ws, "Capacidade Contrib 'Modo Foco' acoplada ao canvas")

        # Fallback: append note to first doc block or create one
        for blk in ws.blocks:
            if blk.type == "doc_editor":
                blk.data["markdown"] = blk.data.get("markdown", "") + f"\n- {command}\n"
                return self.recompute_workspace(ws, f"Contexto incorporado: {command[:50]}")

        ws.blocks.append(
            WorkspaceBlock(
                id=f"blk_ctx_{uuid.uuid4().hex[:6]}",
                type="doc_editor",
                title="Nota Contextual",
                capability="docs_engine",
                col_span=6,
                data={"markdown": f"### Refinamento\n{command}\n"},
            )
        )
        return self.recompute_workspace(ws, f"Refinamento aplicado: {command[:50]}")

    def merge_semantic_into_block(
        self, ws: WorkspaceGraph, block_id: str, semantic_obj_id: str
    ) -> tuple[WorkspaceGraph, str]:
        """Intent Physics: drops a SemanticFS object onto a live block and merges by context."""
        sem_obj = self.semantic_fs.get_object(semantic_obj_id)
        if not sem_obj:
            raise ValueError(f"Semantic object not found: {semantic_obj_id}")

        target_block = next((b for b in ws.blocks if b.id == block_id), None)
        if not target_block:
            raise ValueError(f"Target block not found: {block_id}")

        if target_block.type == "budget_sheet":
            extracted = extract_numeric_items(sem_obj.content_text)
            rows = target_block.data.setdefault("rows", [])
            if extracted:
                for idx, item in enumerate(extracted):
                    rows.append(
                        {
                            "id": f"m_{uuid.uuid4().hex[:5]}_{idx}",
                            "category": "Importado (Física)",
                            "item": item["item"],
                            "qty": 1,
                            "cost": item["cost"],
                        }
                    )
                msg = f"Física de Intenção: {len(extracted)} valor(es) extraído(s) de '{sem_obj.title}' e fundido(s) na planilha."
            else:
                rows.append(
                    {
                        "id": f"m_{uuid.uuid4().hex[:5]}",
                        "category": "Referência",
                        "item": f"Ref: {sem_obj.title}",
                        "qty": 1,
                        "cost": 0.0,
                    }
                )
                msg = f"Física de Intenção: referência '{sem_obj.title}' vinculada à planilha."
            self.recompute_workspace(ws, msg)
            return ws, msg

        if target_block.type == "doc_editor":
            addition = f"\n\n### Contexto Fundido: {sem_obj.title}\n> {sem_obj.summary}\n"
            target_block.data["markdown"] = target_block.data.get("markdown", "") + addition
            msg = f"Física de Intenção: '{sem_obj.title}' fundido no documento."
            self.recompute_workspace(ws, msg)
            return ws, msg

        if target_block.type == "checklist_timeline":
            items = target_block.data.setdefault("items", [])
            items.append(
                {
                    "id": f"m_{uuid.uuid4().hex[:5]}",
                    "day": "Fundido",
                    "title": f"Revisar: {sem_obj.title}",
                    "done": False,
                }
            )
            msg = f"Física de Intenção: '{sem_obj.title}' convertido em etapa do cronograma."
            self.recompute_workspace(ws, msg)
            return ws, msg

        msg = f"Física de Intenção: contexto '{sem_obj.title}' associado ao workspace."
        self.recompute_workspace(ws, msg)
        return ws, msg

    def dissolve_workspace(self, ws: WorkspaceGraph) -> dict[str, Any]:
        """Dissolves the ephemeral UI while archiving its full semantic value in SemanticFS."""
        ws.status = "dissolved"
        lines = [
            f"# Arquivo de Contexto: {ws.title}",
            f"Intenção original: {ws.intent_query}",
            f"Resumo: {ws.essence.headline}",
            "",
        ]
        for blk in ws.blocks:
            lines.append(f"## {blk.title} ({blk.type})")
            if blk.type == "budget_sheet":
                s = blk.data.get("summary", {})
                lines.append(f"Total: {_format_brl(float(s.get('total', 0)))} / Limite: {_format_brl(float(s.get('budget_limit', 0)))}")
                for r in blk.data.get("rows", []):
                    lines.append(f"- {r.get('item')}: {_format_brl(float(r.get('cost', 0)))} x {r.get('qty', 1)}")
            elif blk.type == "doc_editor":
                lines.append(blk.data.get("markdown", ""))
            elif blk.type == "checklist_timeline":
                for it in blk.data.get("items", []):
                    mark = "x" if it.get("done") else " "
                    lines.append(f"- [{mark}] {it.get('day')}: {it.get('title')}")

        archived = self.semantic_fs.ingest_text(
            title=f"Contexto Dissolvido — {ws.title}",
            content_text="\n".join(lines),
            kind="workspace_archive",
            extra_tags=[ws.intent_type, "workspace_dissolvido"],
        )
        return {"workspace_id": ws.id, "status": "dissolved", "archived_semantic_id": archived.id}
