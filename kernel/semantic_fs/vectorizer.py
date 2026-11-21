"""Lightweight local semantic vectorizer (zero external downloads, PT-BR/EN aware)."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata

VECTOR_DIM = 256

# Semantic concept clusters to boost recall across synonyms without external models
_SYNONYM_GROUPS: list[set[str]] = [
    {"viagem", "roteiro", "turismo", "ferias", "hotel", "voo", "passagem", "destino", "travel", "trip"},
    {"orcamento", "custo", "gasto", "financeiro", "dinheiro", "despesa", "planilha", "preco", "budget", "fatura", "boleto"},
    {"contrato", "acordo", "juridico", "clausula", "pdf", "documento", "assinatura", "revisao", "contract"},
    {"trabalho", "projeto", "reuniao", "cliente", "entrega", "prazo", "tarefa", "sprint", "relatorio"},
    {"saude", "exame", "medico", "consulta", "receita", "treino", "dieta"},
    {"casa", "endereco", "moradia", "aluguel", "energia", "agua", "internet"},
    {"codigo", "software", "sistema", "api", "github", "arquitetura", "kernel", "bug", "deploy"},
]

_WORD_TO_CONCEPT: dict[str, str] = {}
for idx, group in enumerate(_SYNONYM_GROUPS):
    concept_key = f"__concept_{idx}__"
    for word in group:
        _WORD_TO_CONCEPT[word] = concept_key

_STOPWORDS = {
    "de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "em", "no", "na", "nos", "nas",
    "um", "uma", "uns", "umas", "para", "por", "com", "que", "se", "ao", "aos", "ou", "como",
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "have", "has",
    "aquele", "aquela", "esse", "essa", "este", "esta", "meu", "minha", "seu", "sua", "sobre",
    "mostre", "mostrar", "ache", "achar", "buscar", "procure", "procurar", "abrir", "abra",
}


def normalize_text(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9\s]", " ", ascii_text)


def tokenize(text: str) -> list[str]:
    norm = normalize_text(text)
    return [tok for tok in norm.split() if len(tok) >= 2 and tok not in _STOPWORDS]


def _hash_feature(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    val = int.from_bytes(digest, "little")
    bucket = val % VECTOR_DIM
    sign = 1.0 if ((val >> 8) & 1) == 0 else -1.0
    return bucket, sign


def embed_text(text: str) -> list[float]:
    """Produces a normalized 256-d semantic vector using tokens, concepts, and char 3-grams."""
    vec = [0.0] * VECTOR_DIM
    tokens = tokenize(text)
    if not tokens:
        return vec

    for tok in tokens:
        # Exact token
        b, s = _hash_feature(f"w:{tok}")
        vec[b] += s * 1.4

        # Stem prefix (helps Portuguese inflections: revisar/revisei/revisao)
        if len(tok) >= 5:
            b, s = _hash_feature(f"st:{tok[:5]}")
            vec[b] += s * 1.0

        # Concept cluster expansion
        concept = _WORD_TO_CONCEPT.get(tok)
        if concept:
            b, s = _hash_feature(concept)
            vec[b] += s * 1.8

        # Character 3-grams for typo tolerance
        padded = f"<{tok}>"
        for i in range(len(padded) - 2):
            b, s = _hash_feature(f"g:{padded[i:i+3]}")
            vec[b] += s * 0.25

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
