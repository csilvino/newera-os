"""Newera OS Kernel Daemon — FastAPI HTTP + WebSocket Server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .capabilities.base import CapabilityRegistry
from .capabilities.builtin.calc_engine import CalcEngine
from .capabilities.builtin.docs_engine import DocsEngine
from .capabilities.builtin.geo_weather_engine import GeoWeatherEngine
from .capabilities.builtin.planner_engine import PlannerEngine
from .config import KernelConfig
from .continuum.manager import ContinuumManager
from .guardian.service import GuardianService
from .intent_engine.llm_bridge import LLMBridge
from .intent_engine.planner import IntentEngine
from .models import IntentRequest, SovereigntyTokenRequest
from .semantic_fs.store import SemanticFS


class RefineRequest(BaseModel):
    command: str


class BlockUpdateRequest(BaseModel):
    data: dict[str, Any]
    summary: str = "Edição direta no bloco"


class PhysicsMergeRequest(BaseModel):
    block_id: str
    semantic_object_id: str


class VaultStoreRequest(BaseModel):
    key: str
    value: str
    category: str = "personal"
    label: str = ""


class PIITestRequest(BaseModel):
    text: str
    target: str = "external_web_service"


class NoteIngestRequest(BaseModel):
    title: str
    content: str
    tags: list[str] = []
    people: list[str] = []


def create_app(data_dir: Path | None = None) -> FastAPI:
    config = KernelConfig.from_env(data_dir=data_dir)
    guardian = GuardianService(config.guardian_dir, config.guardian_db_path)
    semantic_fs = SemanticFS(config.semantic_db_path, config.semantic_store_dir)
    semantic_fs.seed_initial_memories()

    registry = CapabilityRegistry(Path(__file__).resolve().parent / "capabilities")
    registry.register(CalcEngine())
    registry.register(GeoWeatherEngine())
    registry.register(DocsEngine())
    registry.register(PlannerEngine())
    registry.discover_contrib()

    llm_bridge = LLMBridge(config, guardian)
    intent_engine = IntentEngine(registry, semantic_fs, guardian, llm_bridge)
    continuum = ContinuumManager()

    app = FastAPI(
        title="Newera OS Kernel",
        version=__version__,
        description="Intent-Based Operating System Kernel implementing Open Intent Protocol (OIP v0.1).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Expose services on app.state for testing and introspection
    app.state.config = config
    app.state.guardian = guardian
    app.state.semantic_fs = semantic_fs
    app.state.registry = registry
    app.state.intent_engine = intent_engine
    app.state.continuum = continuum

    # --- System Status & Capabilities ---
    @app.get("/api/system/status")
    def system_status() -> dict[str, Any]:
        return {
            "os": "Newera OS",
            "version": __version__,
            "protocol": "OIP v0.1",
            "llm_provider": llm_bridge.active_provider,
            "capabilities": [m.model_dump() for m in registry.list_manifests()],
            "active_workspaces": continuum.list_workspaces(),
            "connected_devices": continuum.list_devices(),
            "guardian": guardian.get_status(),
        }

    # --- Pillar 1: Intent Engine & Generative Workspaces ---
    @app.post("/api/intent")
    async def run_intent(req: IntentRequest) -> dict[str, Any]:
        ws = await intent_engine.plan_workspace(req)
        continuum.save_workspace(ws)
        await continuum.broadcast_workspace(ws)
        return ws.model_dump()

    @app.get("/api/workspaces")
    def list_workspaces() -> list[dict[str, Any]]:
        return continuum.list_workspaces()

    @app.get("/api/workspaces/{ws_id}")
    def get_workspace(ws_id: str) -> dict[str, Any]:
        ws = continuum.get_workspace(ws_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return ws.model_dump()

    @app.post("/api/workspaces/{ws_id}/refine")
    async def refine_workspace(ws_id: str, req: RefineRequest) -> dict[str, Any]:
        ws = continuum.get_workspace(ws_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")
        updated = await intent_engine.refine_workspace(ws, req.command)
        continuum.save_workspace(updated)
        await continuum.broadcast_workspace(updated)
        return updated.model_dump()

    @app.patch("/api/workspaces/{ws_id}/blocks/{block_id}")
    async def update_block(ws_id: str, block_id: str, req: BlockUpdateRequest) -> dict[str, Any]:
        ws = continuum.get_workspace(ws_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")
        blk = next((b for b in ws.blocks if b.id == block_id), None)
        if not blk:
            raise HTTPException(status_code=404, detail="Block not found")
        blk.data = req.data
        updated = intent_engine.recompute_workspace(ws, req.summary)
        continuum.save_workspace(updated)
        await continuum.broadcast_workspace(updated)
        return updated.model_dump()

    @app.post("/api/workspaces/{ws_id}/merge")
    async def physics_merge(ws_id: str, req: PhysicsMergeRequest) -> dict[str, Any]:
        ws = continuum.get_workspace(ws_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")
        try:
            updated, message = intent_engine.merge_semantic_into_block(
                ws, req.block_id, req.semantic_object_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        continuum.save_workspace(updated)
        await continuum.broadcast_workspace(updated)
        return {"workspace": updated.model_dump(), "message": message}

    @app.post("/api/workspaces/{ws_id}/restore/{version}")
    async def restore_workspace_snapshot(ws_id: str, version: int) -> dict[str, Any]:
        try:
            ws = continuum.restore_snapshot(ws_id, version)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await continuum.broadcast_workspace(ws)
        return ws.model_dump()

    @app.post("/api/workspaces/{ws_id}/dissolve")
    async def dissolve_workspace(ws_id: str) -> dict[str, Any]:
        ws = continuum.get_workspace(ws_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")
        res = intent_engine.dissolve_workspace(ws)
        await continuum.broadcast({"type": "workspace_dissolved", "workspace_id": ws_id})
        return res

    # --- Pillar 2: SemanticFS (Folderless Memory & Graph) ---
    @app.get("/api/semantic/objects")
    def list_semantic_objects(limit: int = 50) -> list[dict[str, Any]]:
        return [o.model_dump() for o in semantic_fs.list_objects(limit=limit)]

    @app.get("/api/semantic/search")
    def search_semantic(q: str, limit: int = 10) -> list[dict[str, Any]]:
        return [o.model_dump() for o in semantic_fs.search(q, limit=limit)]

    @app.get("/api/semantic/graph")
    def get_semantic_graph() -> dict[str, Any]:
        return semantic_fs.get_graph()

    @app.post("/api/semantic/notes")
    def ingest_note(req: NoteIngestRequest) -> dict[str, Any]:
        obj = semantic_fs.ingest_text(
            title=req.title,
            content_text=req.content,
            kind="note",
            extra_tags=req.tags,
            extra_people=req.people,
        )
        return obj.model_dump()

    @app.post("/api/semantic/upload")
    async def upload_semantic_file(
        file: UploadFile = File(...),
        tags: str = Form(""),
        people: str = Form(""),
    ) -> dict[str, Any]:
        raw = await file.read()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        people_list = [p.strip() for p in people.split(",") if p.strip()]
        obj = semantic_fs.ingest_bytes(
            data=raw,
            filename=file.filename or "arquivo_sem_nome",
            mime_type=file.content_type or "application/octet-stream",
            extra_tags=tag_list,
            extra_people=people_list,
        )
        return obj.model_dump()

    # --- Pillar 3: Continuum (Multi-Device QR Handoff + WebSockets) ---
    @app.get("/api/continuum/handoff")
    def get_handoff(shell_port: int = 5173, workspace_id: str | None = None) -> dict[str, Any]:
        return continuum.get_handoff_info(shell_port=shell_port, workspace_id=workspace_id)

    @app.websocket("/ws/continuum")
    async def ws_continuum(
        websocket: WebSocket,
        device_type: str = "desktop",
        device_name: str = "Terminal",
    ) -> None:
        client_id = await continuum.register_client(
            websocket, device_type=device_type, device_name=device_name
        )
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            await continuum.unregister_client(client_id)

    # --- Pillar 4: Guardian Sandbox (Vault, PII Proxy, Sovereignty Tokens, Audit) ---
    @app.get("/api/guardian/status")
    def guardian_status() -> dict[str, Any]:
        return guardian.get_status()

    @app.get("/api/guardian/vault")
    def guardian_list_vault() -> list[dict[str, Any]]:
        return guardian.list_vault_items()

    @app.post("/api/guardian/vault")
    def guardian_store_vault(req: VaultStoreRequest) -> dict[str, Any]:
        return guardian.store_vault_item(req.key, req.value, req.category, req.label)

    @app.get("/api/guardian/vault/{key}/reveal")
    def guardian_reveal_vault(key: str) -> dict[str, Any]:
        item = guardian.reveal_vault_item(key)
        if not item:
            raise HTTPException(status_code=404, detail="Vault item not found")
        return item

    @app.delete("/api/guardian/vault/{key}")
    def guardian_delete_vault(key: str) -> dict[str, Any]:
        if not guardian.delete_vault_item(key):
            raise HTTPException(status_code=404, detail="Vault item not found")
        return {"deleted": True, "key": key}

    @app.post("/api/guardian/proxy/sanitize")
    def guardian_sanitize(req: PIITestRequest) -> dict[str, Any]:
        return guardian.sanitize_outbound(req.text, target=req.target)

    @app.get("/api/guardian/tokens")
    def guardian_list_tokens() -> list[dict[str, Any]]:
        return guardian.list_token_requests()

    @app.post("/api/guardian/tokens/request")
    def guardian_request_token(req: SovereigntyTokenRequest) -> dict[str, Any]:
        return guardian.request_sovereignty_token(
            audience=req.audience,
            scope=req.scope,
            vault_keys=req.vault_keys,
            ttl_seconds=req.ttl_seconds,
            reason=req.reason,
        )

    @app.post("/api/guardian/tokens/{request_id}/approve")
    def guardian_approve_token(request_id: str) -> dict[str, Any]:
        try:
            return guardian.approve_token_request(request_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/guardian/tokens/{request_id}/deny")
    def guardian_deny_token(request_id: str) -> dict[str, Any]:
        return guardian.deny_token_request(request_id)

    @app.post("/api/guardian/tokens/verify")
    def guardian_verify_token(payload: dict[str, str]) -> dict[str, Any]:
        return guardian.verify_token(payload.get("token", ""))

    @app.get("/api/guardian/audit")
    def guardian_audit(limit: int = 50) -> list[dict[str, Any]]:
        return guardian.get_audit_log(limit=limit)

    # Serve production shell build if present
    shell_dist = config.root_dir / "shell" / "dist"
    if shell_dist.exists():
        app.mount("/", StaticFiles(directory=str(shell_dist), html=True), name="shell")

    return app


app = create_app()
