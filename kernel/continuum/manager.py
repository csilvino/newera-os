"""Continuum Manager — Active Workspaces, WebSocket Sync, Time-Travel, and QR Code Handoff."""

from __future__ import annotations

import copy
import io
import socket
import uuid
from typing import Any

import qrcode
import qrcode.image.svg
from fastapi import WebSocket

from ..models import WorkspaceGraph, utc_now_iso


def get_local_lan_ip() -> str:
    """Detects LAN IP so phones/tablets on the same Wi-Fi can connect via QR Code."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def generate_qr_svg(url: str) -> str:
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(url, image_factory=factory, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


class ContinuumManager:
    """Manages active ephemeral workspaces and real-time multi-device WebSocket sync."""

    def __init__(self) -> None:
        self.workspaces: dict[str, WorkspaceGraph] = {}
        self.clients: dict[str, dict[str, Any]] = {}

    def save_workspace(self, ws: WorkspaceGraph) -> WorkspaceGraph:
        self.workspaces[ws.id] = ws
        return ws

    def get_workspace(self, ws_id: str) -> WorkspaceGraph | None:
        return self.workspaces.get(ws_id)

    def list_workspaces(self) -> list[dict[str, Any]]:
        return [
            {
                "id": ws.id,
                "title": ws.title,
                "intent_type": ws.intent_type,
                "status": ws.status,
                "version": ws.version,
                "updated_at": ws.updated_at,
                "headline": ws.essence.headline,
                "blocks_count": len(ws.blocks),
            }
            for ws in sorted(self.workspaces.values(), key=lambda w: w.updated_at, reverse=True)
            if ws.status == "active"
        ]

    def restore_snapshot(self, ws_id: str, version: int) -> WorkspaceGraph:
        """Time-Travel: restores a workspace to any previous snapshot version."""
        ws = self.workspaces.get(ws_id)
        if not ws:
            raise ValueError(f"Workspace not found: {ws_id}")
        snap = next((s for s in ws.history if s.version == version), None)
        if not snap:
            raise ValueError(f"Snapshot version {version} not found")
        ws.blocks = copy.deepcopy(snap.blocks)
        ws.essence = copy.deepcopy(snap.essence)
        ws.updated_at = utc_now_iso()
        return ws

    async def register_client(
        self, websocket: WebSocket, device_type: str = "desktop", device_name: str = "Terminal"
    ) -> str:
        await websocket.accept()
        client_id = f"dev_{uuid.uuid4().hex[:8]}"
        self.clients[client_id] = {
            "id": client_id,
            "ws": websocket,
            "device_type": device_type,
            "device_name": device_name,
            "connected_at": utc_now_iso(),
        }
        await self.broadcast({"type": "presence_update", "devices": self.list_devices()})
        return client_id

    async def unregister_client(self, client_id: str) -> None:
        self.clients.pop(client_id, None)
        await self.broadcast({"type": "presence_update", "devices": self.list_devices()})

    def list_devices(self) -> list[dict[str, Any]]:
        return [
            {
                "id": c["id"],
                "device_type": c["device_type"],
                "device_name": c["device_name"],
                "connected_at": c["connected_at"],
            }
            for c in self.clients.values()
        ]

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[str] = []
        for cid, info in list(self.clients.items()):
            try:
                await info["ws"].send_json(message)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.clients.pop(cid, None)

    async def broadcast_workspace(self, ws: WorkspaceGraph) -> None:
        await self.broadcast({"type": "workspace_sync", "workspace": ws.model_dump()})

    def get_handoff_info(self, shell_port: int = 5173, workspace_id: str | None = None) -> dict[str, Any]:
        lan_ip = get_local_lan_ip()
        base_url = f"http://{lan_ip}:{shell_port}"
        if workspace_id:
            url = f"{base_url}/?ws={workspace_id}&device=mobile"
        else:
            url = f"{base_url}/?device=mobile"
        return {
            "lan_ip": lan_ip,
            "url": url,
            "qr_svg": generate_qr_svg(url),
            "connected_devices": self.list_devices(),
        }
