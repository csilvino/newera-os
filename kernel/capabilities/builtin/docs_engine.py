"""Documents & Semantic Knowledge Capability Engine."""

from __future__ import annotations

from ...models import CapabilityManifest, CapabilityPermission, WorkspaceBlock
from ..base import CapabilityContext, CapabilityEngine


class DocsEngine(CapabilityEngine):
    manifest = CapabilityManifest(
        id="docs_engine",
        name="Motor de Documentos & Conhecimento",
        version="0.1.0",
        description="Edição rica de documentos, revisão de arquivos do SemanticFS e síntese contextual.",
        intents=["document_work", "semantic_recall", "general_workspace"],
        keywords=["documento", "contrato", "pdf", "texto", "escrever", "revisar", "relatorio", "nota"],
        permissions=CapabilityPermission(network=False, vault="none", semantic_fs="read_write"),
        source="builtin",
    )

    async def execute(self, ctx: CapabilityContext) -> list[WorkspaceBlock]:
        blocks: list[WorkspaceBlock] = []

        if ctx.semantic_hits:
            top = ctx.semantic_hits[0]
            blocks.append(
                WorkspaceBlock(
                    id="blk_semantic_doc",
                    type="semantic_viewer",
                    title=f"Memória Encontrada — {top.title}",
                    capability=self.manifest.id,
                    col_span=7,
                    data={
                        "object_id": top.id,
                        "title": top.title,
                        "kind": top.kind,
                        "mime_type": top.mime_type,
                        "original_name": top.original_name,
                        "content_text": top.content_text,
                        "entities": top.entities,
                        "tags": top.tags,
                        "score": top.score,
                        "created_at": top.created_at,
                        "other_matches": [
                            {
                                "id": h.id,
                                "title": h.title,
                                "summary": h.summary,
                                "score": h.score,
                                "kind": h.kind,
                            }
                            for h in ctx.semantic_hits[1:5]
                        ],
                    },
                )
            )
            blocks.append(
                WorkspaceBlock(
                    id="blk_notes",
                    type="doc_editor",
                    title="Notas & Ações sobre este Contexto",
                    capability=self.manifest.id,
                    col_span=5,
                    accepts_drop=["document", "note", "dataset"],
                    data={
                        "markdown": (
                            f"# Revisão: {top.title}\n\n"
                            f"- **Contexto buscado:** {ctx.query}\n"
                            f"- **Tags detectadas:** {', '.join(top.tags) or 'nenhuma'}\n"
                            f"- **Pessoas ligadas:** {', '.join(top.entities.get('people', [])) or 'nenhuma'}\n\n"
                            "## Próximas anotações\n"
                            "- "
                        )
                    },
                )
            )
            return blocks

        # Default rich document workspace
        blocks.append(
            WorkspaceBlock(
                id="blk_editor",
                type="doc_editor",
                title="Espaço Vivo de Documento",
                capability=self.manifest.id,
                col_span=8,
                accepts_drop=["document", "note", "dataset"],
                data={
                    "markdown": (
                        f"# {ctx.query.strip().capitalize()}\n\n"
                        "## Objetivo\n"
                        "Escreva, arraste memórias do SemanticFS para fundir contexto ou refine esta tela pela barra de intenção.\n\n"
                        "## Pontos-Chave\n"
                        "- Item 1\n"
                        "- Item 2\n"
                    )
                },
            )
        )
        return blocks
