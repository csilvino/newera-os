"""Community Plugin Skill: Stop currently playing background music."""

from __future__ import annotations

from pathlib import Path

IPC_CMD_FILE = Path(__file__).resolve().parent.parent / "data" / "ipc" / "voice_cmd.txt"

SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "stop_music",
        "description": "Para ou pausa a música que está tocando no momento.",
        "parameters": {"type": "object", "properties": {}},
    },
}

KEYWORDS = [
    "parar musica",
    "parar música",
    "pare a musica",
    "pare a música",
    "pausar musica",
    "silenciar musica",
    "fechar player",
    "fechar video",
    "fechar vídeo",
    "parar video",
    "parar vídeo",
]


def run(_args: dict) -> str:
    IPC_CMD_FILE.parent.mkdir(parents=True, exist_ok=True)
    IPC_CMD_FILE.write_text("STOP_MUSIC|", encoding="utf-8")
    return "RESP|plugin:youtube|Player YouTube|Player encerrado."
