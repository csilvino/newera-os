"""Kernel configuration and directory bootstrap."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KernelConfig:
    root_dir: Path
    data_dir: Path
    semantic_db_path: Path
    semantic_store_dir: Path
    guardian_dir: Path
    guardian_db_path: Path
    host: str = "0.0.0.0"
    port: int = 8765
    llm_provider: str = "local"  # local | ollama | gemini | openai
    llm_model: str = ""
    ollama_url: str = "http://localhost:11434"
    gemini_api_key: str = ""
    openai_api_key: str = ""

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> "KernelConfig":
        root = Path(__file__).resolve().parent.parent
        base_data = data_dir or Path(os.getenv("NEWERA_DATA_DIR", root / "data"))
        semantic_store = base_data / "semantic_store"
        guardian_dir = base_data / "guardian"
        base_data.mkdir(parents=True, exist_ok=True)
        semantic_store.mkdir(parents=True, exist_ok=True)
        guardian_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            root_dir=root,
            data_dir=base_data,
            semantic_db_path=base_data / "semantic.db",
            semantic_store_dir=semantic_store,
            guardian_dir=guardian_dir,
            guardian_db_path=guardian_dir / "guardian.db",
            host=os.getenv("NEWERA_HOST", "0.0.0.0"),
            port=int(os.getenv("NEWERA_PORT", "8765")),
            llm_provider=os.getenv("NEWERA_LLM_PROVIDER", "local").lower(),
            llm_model=os.getenv("NEWERA_LLM_MODEL", ""),
            ollama_url=os.getenv("NEWERA_OLLAMA_URL", "http://localhost:11434"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        )
