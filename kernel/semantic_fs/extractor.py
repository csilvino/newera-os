"""Content and entity extractor for folderless semantic ingestion."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from pypdf import PdfReader


def extract_text_from_bytes(data: bytes, filename: str, mime_type: str = "") -> tuple[str, str]:
    """Extracts readable text and detects semantic kind from raw file bytes."""
    lower = filename.lower()
    if lower.endswith(".pdf") or mime_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(p.strip() for p in pages if p.strip())
            return text or f"[Documento PDF: {filename}]", "document"
        except Exception:
            return f"[Documento PDF não textual: {filename}]", "document"

    if lower.endswith(".csv") or mime_type == "text/csv":
        decoded = data.decode("utf-8", errors="replace")
        rows = list(csv.reader(io.StringIO(decoded)))
        preview = "\n".join(", ".join(r) for r in rows[:50])
        return preview, "dataset"

    if lower.endswith(".json") or mime_type == "application/json":
        decoded = data.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(decoded)
            return json.dumps(parsed, ensure_ascii=False, indent=2)[:8000], "dataset"
        except Exception:
            return decoded[:8000], "dataset"

    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")) or mime_type.startswith("image/"):
        return f"Imagem armazenada no SemanticFS: {filename} ({len(data)} bytes)", "media"

    decoded = data.decode("utf-8", errors="replace")
    kind = "note" if lower.endswith((".md", ".txt")) else "document"
    return decoded[:20000], kind


_MONEY_RE = re.compile(r"R\$\s?[\d\.,]+", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b")
_PERSON_CUE_RE = re.compile(
    r"\b(?:com\s+(?:o|a)\s+|para\s+(?:o|a)\s+|revisado\s+com\s+|enviado\s+por\s+|cliente\s+|autor:\s*)([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+)?)"
)
_KNOWN_TOPICS = {
    "contrato": ["contrato", "cláusula", "clausula", "assinatura", "acordo"],
    "viagem": ["viagem", "roteiro", "hotel", "voo", "destino", "turismo"],
    "finanças": ["orçamento", "orcamento", "fatura", "custo", "pagamento", "r$", "planilha"],
    "projeto": ["projeto", "arquitetura", "sistema", "entrega", "cronograma", "código"],
    "pessoal": ["casa", "saúde", "saude", "família", "familia", "lembrete"],
}


def extract_entities(title: str, text: str) -> tuple[dict[str, list[str]], list[str]]:
    """Extracts people, monetary amounts, dates, and topical tags locally."""
    combined = f"{title}\n{text}"
    people = sorted({m.group(1).strip() for m in _PERSON_CUE_RE.finditer(combined)})
    amounts = sorted({m.group(0).strip() for m in _MONEY_RE.finditer(combined)})[:10]
    dates = sorted({m.group(0).strip() for m in _DATE_RE.finditer(combined)})[:10]

    lower = combined.lower()
    tags: list[str] = []
    for topic, cues in _KNOWN_TOPICS.items():
        if any(cue in lower for cue in cues):
            tags.append(topic)

    entities: dict[str, list[str]] = {}
    if people:
        entities["people"] = people
    if amounts:
        entities["amounts"] = amounts
    if dates:
        entities["dates"] = dates

    return entities, tags


def build_summary(text: str, max_chars: int = 220) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def extract_numeric_items(text: str) -> list[dict[str, Any]]:
    """Extracts line-item monetary values from a document (used by Intent Physics drop-to-merge)."""
    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = _MONEY_RE.search(line)
        if not match:
            continue
        raw_val = match.group(0).replace("R$", "").replace("r$", "").strip()
        # Handle Brazilian formatting: 1.250,50 -> 1250.50
        if "," in raw_val:
            normalized = raw_val.replace(".", "").replace(",", ".")
        else:
            normalized = raw_val.replace(".", "")
        try:
            amount = float(normalized)
        except ValueError:
            continue
        label = line.replace(match.group(0), "").strip(" -:|•\t")
        items.append({"item": label[:60] or "Item importado", "cost": amount})
    return items
