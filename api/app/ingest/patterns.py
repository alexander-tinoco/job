"""Deterministic injection patterns.

These **flag, they never reject**. A false positive removes a real person from a
hiring process, which is a far worse outcome than an evaluation that carries a
warning. Pattern matching also cannot be exhaustive — there is no list that
covers every way to phrase an instruction — which is exactly why it is the
weakest of the four layers and why the other three do the real work (plan §6).
"""

from __future__ import annotations

import re

# Bilingual on purpose: the product is sold in Spanish-speaking markets and the
# payload is written in whatever language the attacker assumes we read.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override_instructions",
        re.compile(
            r"\b(ignore|disregard|forget)\s+(all\s+)?(the\s+)?(previous|prior|above)\b", re.I
        ),
    ),
    (
        "override_instructions_es",
        re.compile(r"\b(ignora|olvida|descarta)\s+(las\s+)?(instrucciones|indicaciones)\b", re.I),
    ),
    (
        "role_assignment",
        re.compile(r"\b(you\s+are\s+now|act\s+as|eres\s+un|act[u\u00fa]a\s+como)\b", re.I),
    ),
    ("chat_role_marker", re.compile(r"^\s*(system|assistant|developer|user)\s*:", re.I | re.M)),
    (
        "scoring_command",
        re.compile(
            r"\b(score|rate|puntuaci[o\u00f3]n|calificaci[o\u00f3]n)\s*[:=]?\s*(10|max|100)\b", re.I
        ),
    ),
    (
        "approval_command",
        re.compile(r"\b(approve|recommend|hire|contrata|aprueba)\s+(this|el|este)\b", re.I),
    ),
    (
        "ideal_candidate_claim",
        re.compile(r"\b(ideal|perfect|best)\s+(candidate|fit|match)\b", re.I),
    ),
    ("delimiter_spoofing", re.compile(r"</?\s*(resume|cv|candidate|instructions?)\s*>", re.I)),
    ("prompt_leak_request", re.compile(r"\b(system\s+prompt|your\s+instructions)\b", re.I)),
)


def find_patterns(text: str) -> list[str]:
    """Names of the patterns present in `text`, in a stable order."""
    return [name for name, pattern in PATTERNS if pattern.search(text)]


# Tags that would let a résumé close our own delimiter and start giving orders.
_DELIMITER = re.compile(r"</?\s*(resume|cv|candidate|instructions?)\s*>", re.I)


def strip_delimiter_spoofing(text: str) -> str:
    """Neutralise tags that imitate the delimiters wrapping the résumé in the prompt.

    Removed rather than escaped: nothing of value is lost, and an escaped tag is
    one decoding bug away from being a tag again.
    """
    return _DELIMITER.sub(" ", text)
