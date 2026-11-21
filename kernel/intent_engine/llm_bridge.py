"""Optional LLM Bridge (Local Ollama, Gemini, OpenAI) always routed through Guardian PII Proxy."""

from __future__ import annotations

from typing import Any

import httpx

from ..config import KernelConfig
from ..guardian.service import GuardianService


class LLMBridge:
    """Optional LLM enrichment. Falls back silently to 100% local mode if unconfigured."""

    def __init__(self, config: KernelConfig, guardian: GuardianService) -> None:
        self.config = config
        self.guardian = guardian

    @property
    def active_provider(self) -> str:
        if self.config.llm_provider == "gemini" and self.config.gemini_api_key:
            return "gemini"
        if self.config.llm_provider == "openai" and self.config.openai_api_key:
            return "openai"
        if self.config.llm_provider == "ollama":
            return "ollama"
        return "local_deterministic"

    async def enrich_headline(self, query: str, intent_type: str) -> dict[str, Any]:
        provider = self.active_provider
        if provider == "local_deterministic":
            return {"used_llm": False, "provider": provider, "text": None, "pii_redacted": 0}

        # Guardian mandatory outbound sanitization
        sanitized = self.guardian.sanitize_outbound(query, target=f"llm:{provider}")
        safe_prompt = (
            f"Resuma em uma frase curta e amigável em português o objetivo da tarefa "
            f"(tipo={intent_type}): {sanitized['sanitized_text']}"
        )

        try:
            if provider == "ollama":
                model = self.config.llm_model or "llama3.2"
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.post(
                        f"{self.config.ollama_url.rstrip('/')}/api/generate",
                        json={"model": model, "prompt": safe_prompt, "stream": False},
                    )
                    text = resp.json().get("response", "").strip()
                    return {"used_llm": bool(text), "provider": "ollama", "text": text or None, "pii_redacted": sanitized["redacted_count"]}

            if provider == "gemini":
                model = self.config.llm_model or "gemini-2.0-flash"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        params={"key": self.config.gemini_api_key},
                        json={"contents": [{"parts": [{"text": safe_prompt}]}]},
                    )
                    data = resp.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return {"used_llm": True, "provider": "gemini", "text": text, "pii_redacted": sanitized["redacted_count"]}

            if provider == "openai":
                model = self.config.llm_model or "gpt-4o-mini"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                        json={"model": model, "messages": [{"role": "user", "content": safe_prompt}]},
                    )
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    return {"used_llm": True, "provider": "openai", "text": text, "pii_redacted": sanitized["redacted_count"]}
        except Exception:
            pass

        return {"used_llm": False, "provider": "local_deterministic", "text": None, "pii_redacted": sanitized["redacted_count"]}
