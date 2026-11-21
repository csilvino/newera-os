"""Community Plugin Skill: Search YouTube & Play Video in a clean standalone Player window."""

from __future__ import annotations

from pathlib import Path

IPC_CMD_FILE = Path(__file__).resolve().parent.parent / "data" / "ipc" / "voice_cmd.txt"

SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "play_youtube_music",
        "description": "Pesquisa uma música, artista ou vídeo no YouTube e abre o player de vídeo reproduzindo automaticamente.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nome da música, artista ou vídeo (ex: 'Coldplay Viva la Vida', 'lofi hip hop')"},
            },
            "required": ["query"],
        },
    },
}

KEYWORDS = ["toque ", "tocar ", "coloque musica", "coloque música", "youtube ", "ouvir ", "reproduzir ", "video ", "vídeo "]


def run(args: dict) -> str:
    query = str(args.get("query") or "lofi chill beats").strip()
    IPC_CMD_FILE.parent.mkdir(parents=True, exist_ok=True)
    IPC_CMD_FILE.write_text(f"PLAY_YT|{query}", encoding="utf-8")
    return f"RESP|plugin:youtube|Player YouTube|Abrindo '{query}' no player de vídeo."
