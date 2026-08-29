"""Verify what the model said, then compute the number it was not allowed to say.

Layers 3 and 4 of the anti-injection design (plan §6), and both are ordinary
Python. The model rates criteria and quotes the résumé; this module checks every
quote against the source text and applies the rubric weights.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.ai.schema import MAX_SCORE, CriterionAssessment, EvaluationOutput

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class VerifiedQuote:
    quote: str
    found: bool
    start: int | None
    end: int | None


@dataclass(frozen=True)
class VerifiedCriterion:
    criterion_name: str
    matched_rubric: bool
    score: int
    weight: int
    justification: str
    quotes: tuple[VerifiedQuote, ...]


@dataclass(frozen=True)
class VerifiedEvaluation:
    overall_score: Decimal
    criteria: tuple[VerifiedCriterion, ...]
    needs_human_review: bool
    review_reasons: tuple[str, ...]


def normalise(text: str) -> tuple[str, list[int]]:
    """Collapse runs of whitespace, keeping a map back to the original offsets.

    Extraction rebuilds line breaks from the PDF's geometry (plan §4), so a
    résumé line the model quotes as "six years of Python" may contain a newline
    in the stored text. Comparing raw would fail almost every genuine quote and
    make the check useless, so both sides are normalised — but the offsets that
    come back point into the original text, because that is what the panel
    highlights.
    """
    characters: list[str] = []
    offsets: list[int] = []
    previous_was_space = False
    for index, character in enumerate(text):
        if character.isspace():
            if previous_was_space:
                continue
            characters.append(" ")
            offsets.append(index)
            previous_was_space = True
        else:
            characters.append(character)
            offsets.append(index)
            previous_was_space = False
    return "".join(characters), offsets


def _fold(text: str, offsets: list[int]) -> tuple[str, list[int]]:
    """Lower-case the text while keeping one offset per resulting character.

    `str.lower()` is not length-preserving: `"İ".lower()` is two characters, an
    `i` and a combining dot. Searching a lowered string and then indexing an
    offset map built from the original therefore runs off the end — which it
    did, raising `IndexError` out of `verify()` and, from the batch collector,
    losing the whole tick rather than one row. A Turkish name in a résumé was
    enough to trigger it.
    """
    folded: list[str] = []
    mapped: list[int] = []
    for character, offset in zip(text, offsets, strict=True):
        lowered = character.lower()
        folded.append(lowered)
        mapped.extend([offset] * len(lowered))
    return "".join(folded), mapped


def find_quote(quote: str, source: str) -> VerifiedQuote:
    """Locate a quote in the résumé, or report that it is not there.

    Matched case-insensitively: a model that capitalises a sentence start has
    not fabricated anything, while a fabricated quote fails either way. What is
    being caught here is invention, not typography.
    """
    stripped = quote.strip()
    if not stripped:
        return VerifiedQuote(quote=quote, found=False, start=None, end=None)

    flat_source, offsets = normalise(source)
    flat_quote, quote_offsets = normalise(stripped)
    folded_source, folded_offsets = _fold(flat_source, offsets)
    folded_quote, _ = _fold(flat_quote, quote_offsets)

    position = folded_source.find(folded_quote)
    if position < 0 or not folded_quote:
        return VerifiedQuote(quote=quote, found=False, start=None, end=None)

    last = position + len(folded_quote) - 1
    return VerifiedQuote(
        quote=quote,
        found=True,
        start=folded_offsets[position],
        end=folded_offsets[last] + 1,
    )


def weighted_score(criteria: tuple[VerifiedCriterion, ...]) -> Decimal:
    """Turn 0-5 ratings into the 0-100 that orders the ranking.

    This is the number the model is never allowed to emit (plan §6, layer 3).
    Weights sum to 100 by construction (Phase 2 validates it), so a perfect
    candidate scores exactly 100.
    """
    total = sum(Decimal(c.score) / MAX_SCORE * c.weight for c in criteria)
    return Decimal(total).quantize(Decimal("0.01"))


def verify(
    output: EvaluationOutput,
    resume_text: str,
    weights: dict[str, int],
) -> VerifiedEvaluation:
    """Check every quote, match every criterion, and compute the overall score."""
    by_name = {name.strip().lower(): weight for name, weight in weights.items()}
    seen: set[str] = set()
    verified: list[VerifiedCriterion] = []
    reasons: list[str] = []

    for assessment in output.criteria:
        key = assessment.criterion_name.strip().lower()
        matched = key in by_name
        if matched:
            seen.add(key)
        else:
            reasons.append(
                f"The model scored '{assessment.criterion_name}', which is not in the rubric."
            )
        verified.append(_verify_one(assessment, resume_text, by_name.get(key, 0), matched))

    for missing in sorted(set(by_name) - seen):
        reasons.append(f"The model did not score the rubric criterion '{missing}'.")

    unverified = [
        quote.quote for criterion in verified for quote in criterion.quotes if not quote.found
    ]
    reasons.extend(f"Evidence not found verbatim in the résumé: {quote!r}" for quote in unverified)

    return VerifiedEvaluation(
        overall_score=weighted_score(tuple(verified)),
        criteria=tuple(verified),
        needs_human_review=bool(reasons),
        review_reasons=tuple(reasons),
    )


def _verify_one(
    assessment: CriterionAssessment, resume_text: str, weight: int, matched: bool
) -> VerifiedCriterion:
    return VerifiedCriterion(
        criterion_name=assessment.criterion_name,
        matched_rubric=matched,
        score=assessment.score,
        weight=weight,
        justification=assessment.justification,
        quotes=tuple(find_quote(quote, resume_text) for quote in assessment.evidence),
    )
