"""Open Intent Protocol (OIP v0.1) data models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntentRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language user intent")
    locale: str = "pt-BR"
    device_type: Literal["desktop", "mobile", "tablet", "voice"] = "desktop"
    workspace_id: str | None = None
    context_refs: list[str] = Field(default_factory=list)


class EssenceMetric(BaseModel):
    label: str
    value: str
    status: Literal["ok", "warn", "alert", "info"] = "info"


class WorkspaceEssence(BaseModel):
    headline: str
    subheadline: str = ""
    metrics: list[EssenceMetric] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class WorkspaceBlock(BaseModel):
    id: str
    type: str
    title: str
    capability: str
    col_span: int = 6
    data: dict[str, Any] = Field(default_factory=dict)
    accepts_drop: list[str] = Field(default_factory=list)


class DataWire(BaseModel):
    id: str
    from_block: str
    from_field: str
    to_block: str
    to_field: str
    label: str


class ExecutionTraceStep(BaseModel):
    step: str
    component: str
    duration_ms: float
    detail: str
    privacy_checked: bool = True


class WorkspaceSnapshot(BaseModel):
    version: int
    timestamp: str = Field(default_factory=utc_now_iso)
    summary: str
    blocks: list[WorkspaceBlock]
    essence: WorkspaceEssence


class WorkspaceGraph(BaseModel):
    id: str
    title: str
    intent_query: str
    intent_type: str
    status: Literal["active", "dissolved"] = "active"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    version: int = 1
    essence: WorkspaceEssence
    blocks: list[WorkspaceBlock] = Field(default_factory=list)
    wires: list[DataWire] = Field(default_factory=list)
    semantic_sources: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[ExecutionTraceStep] = Field(default_factory=list)
    history: list[WorkspaceSnapshot] = Field(default_factory=list)


class CapabilityPermission(BaseModel):
    network: bool = False
    vault: Literal["none", "token_only"] = "none"
    semantic_fs: Literal["none", "read", "read_write"] = "read"


class CapabilityManifest(BaseModel):
    id: str
    name: str
    version: str = "0.1.0"
    description: str
    intents: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    permissions: CapabilityPermission = Field(default_factory=CapabilityPermission)
    source: Literal["builtin", "contrib"] = "builtin"


class SemanticObject(BaseModel):
    id: str
    content_hash: str
    kind: Literal["document", "note", "workspace_archive", "dataset", "media"] = "document"
    title: str
    summary: str
    content_text: str
    mime_type: str = "text/plain"
    original_name: str = ""
    entities: dict[str, list[str]] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    score: float | None = None


class SemanticRelation(BaseModel):
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0
    created_at: str = Field(default_factory=utc_now_iso)


class SovereigntyTokenRequest(BaseModel):
    audience: str = Field(..., min_length=1, description="External service or recipient")
    scope: str = Field(..., min_length=1, description="Minimal claim, e.g. address_verified, payment_auth")
    vault_keys: list[str] = Field(default_factory=list)
    ttl_seconds: int = Field(default=300, ge=30, le=3600)
    reason: str = ""
