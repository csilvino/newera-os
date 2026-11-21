"""Capability SDK base classes and automatic capability discovery."""

from __future__ import annotations

import importlib.util
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..models import CapabilityManifest, CapabilityPermission, SemanticObject, WorkspaceBlock


@dataclass
class CapabilityContext:
    query: str
    intent_type: str
    params: dict[str, Any] = field(default_factory=dict)
    semantic_hits: list[SemanticObject] = field(default_factory=list)
    device_type: str = "desktop"


class CapabilityEngine(ABC):
    """Base contract for every native or community-contributed capability."""

    manifest: CapabilityManifest

    @abstractmethod
    async def execute(self, ctx: CapabilityContext) -> list[WorkspaceBlock]:
        """Generates one or more live WorkspaceBlocks for the given intent context."""


class CapabilityRegistry:
    """Discovers, validates, and serves builtin + community contrib capabilities."""

    def __init__(self, capabilities_root: Path) -> None:
        self.capabilities_root = capabilities_root
        self._engines: dict[str, CapabilityEngine] = {}

    def register(self, engine: CapabilityEngine) -> None:
        self._engines[engine.manifest.id] = engine

    def get(self, cap_id: str) -> CapabilityEngine | None:
        return self._engines.get(cap_id)

    def list_manifests(self) -> list[CapabilityManifest]:
        return [e.manifest for e in self._engines.values()]

    def find_by_intent(self, intent_type: str) -> list[CapabilityEngine]:
        return [e for e in self._engines.values() if intent_type in e.manifest.intents]

    def match_contrib_by_query(self, query_lower: str) -> list[CapabilityEngine]:
        matched: list[CapabilityEngine] = []
        for engine in self._engines.values():
            if engine.manifest.source != "contrib":
                continue
            if any(kw.lower() in query_lower for kw in engine.manifest.keywords):
                matched.append(engine)
        return matched

    def discover_contrib(self) -> list[str]:
        """Auto-discovers community capabilities under kernel/capabilities/contrib/<id>/."""
        contrib_dir = self.capabilities_root / "contrib"
        loaded: list[str] = []
        if not contrib_dir.exists():
            return loaded

        for folder in sorted(contrib_dir.iterdir()):
            if not folder.is_dir():
                continue
            manifest_path = folder / "capability.yaml"
            engine_path = folder / "engine.py"
            if not (manifest_path.exists() and engine_path.exists()):
                continue
            try:
                raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                perms = CapabilityPermission(**(raw_manifest.get("permissions") or {}))
                manifest = CapabilityManifest(
                    id=raw_manifest["id"],
                    name=raw_manifest["name"],
                    version=str(raw_manifest.get("version", "0.1.0")),
                    description=raw_manifest.get("description", ""),
                    intents=list(raw_manifest.get("intents") or []),
                    keywords=list(raw_manifest.get("keywords") or []),
                    permissions=perms,
                    source="contrib",
                )
                mod_name = f"newera_contrib_{manifest.id}"
                spec = importlib.util.spec_from_file_location(mod_name, engine_path)
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                spec.loader.exec_module(module)
                factory = getattr(module, "create_capability", None)
                if callable(factory):
                    engine = factory(manifest)
                    self.register(engine)
                    loaded.append(manifest.id)
            except Exception as exc:
                print(f"[CapabilityRegistry] Failed to load contrib '{folder.name}': {exc}")
        return loaded
