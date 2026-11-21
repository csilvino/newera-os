"""Community-contributed capability example: Deep Focus & Pomodoro Timer."""

from __future__ import annotations

from kernel.capabilities.base import CapabilityContext, CapabilityEngine
from kernel.models import CapabilityManifest, WorkspaceBlock


class FocusPomodoroEngine(CapabilityEngine):
    def __init__(self, manifest: CapabilityManifest) -> None:
        self.manifest = manifest

    async def execute(self, ctx: CapabilityContext) -> list[WorkspaceBlock]:
        minutes = int(ctx.params.get("minutes", 25))
        return [
            WorkspaceBlock(
                id="blk_focus_timer",
                type="focus_timer",
                title="Sessão de Foco Profundo (Contrib SDK)",
                capability=self.manifest.id,
                col_span=6,
                data={
                    "duration_minutes": minutes,
                    "goal": ctx.query,
                    "cycles": 4,
                    "break_minutes": 5,
                },
            )
        ]


def create_capability(manifest: CapabilityManifest) -> CapabilityEngine:
    return FocusPomodoroEngine(manifest)
