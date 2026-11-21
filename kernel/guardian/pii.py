"""Local PII detection and redaction proxy (zero external calls)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PIIMatch:
    kind: str
    value: str
    replacement: str


_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("CPF", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("CNPJ", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE_BR", re.compile(r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)(?:9\d{4}|\d{4})-?\d{4}\b")),
    ("CEP", re.compile(r"\b\d{5}-\d{3}\b")),
    ("API_KEY", re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z\-_]{20,})\b")),
]


def _luhn_valid(digits: str) -> bool:
    nums = [int(ch) for ch in digits if ch.isdigit()]
    if len(nums) < 13 or len(nums) > 16:
        return False
    checksum = 0
    parity = len(nums) % 2
    for idx, n in enumerate(nums):
        if idx % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        checksum += n
    return checksum % 10 == 0


def inspect_and_redact(text: str) -> tuple[str, list[PIIMatch]]:
    """Scans text locally for sensitive PII and replaces matches with pseudonymous tokens."""
    redacted = text
    matches: list[PIIMatch] = []
    counters: dict[str, int] = {}

    for kind, pattern in _PATTERNS:
        def _repl(match: re.Match[str], _kind: str = kind) -> str:
            val = match.group(0)
            if _kind == "CREDIT_CARD" and not _luhn_valid(val):
                return val
            counters[_kind] = counters.get(_kind, 0) + 1
            token = f"[GUARDIAN_{_kind}_{counters[_kind]}]"
            matches.append(PIIMatch(kind=_kind, value=val, replacement=token))
            return token

        redacted = pattern.sub(_repl, redacted)

    return redacted, matches
