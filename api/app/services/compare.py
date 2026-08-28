"""Put two candidates beside each other and say where the gap comes from.

The real question a reviewer has is not "is this one good" but "this one or that
one". Two scores answer neither: 90 against 71 says nothing about *why*.

Because the overall score is a weighted sum, the gap decomposes exactly. Each
criterion contributes `(score / 5) × weight`, so the difference between two
candidates is the sum of per-criterion differences — and one of them is usually
the whole story.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.schema import MAX_SCORE
from app.db.models import Application, Criterion, Evaluation, JobOpening
from app.schemas.compare import (
    ComparedCandidate,
    ComparedCriterion,
    ComparisonOut,
    SideEvidence,
)

MAX_SIDES = 3


class TooManyError(ValueError):
    """More columns than a person can hold in their head at once."""


class NotComparableError(ValueError):
    """One of these has no evaluation yet, so there is nothing to line up."""


def contribution(score: int, weight: int) -> Decimal:
    """What one criterion adds to the overall score."""
    return (Decimal(score) / MAX_SCORE * weight).quantize(Decimal("0.01"))


def compare(session: Session, opening: JobOpening, ids: list[uuid.UUID]) -> ComparisonOut:
    if len(ids) > MAX_SIDES:
        raise TooManyError(f"Compare at most {MAX_SIDES} candidates at once.")

    applications = list(
        session.scalars(
            select(Application)
            .where(Application.id.in_(ids), Application.job_opening_id == opening.id)
            .options(
                selectinload(Application.candidate),
                selectinload(Application.decision),
                selectinload(Application.integrity),
                selectinload(Application.evaluation).selectinload(Evaluation.scores),
            )
        )
    )
    # Keep the caller's order: they chose which column sits on the left.
    by_id = {a.id: a for a in applications}
    ordered = [by_id[i] for i in ids if i in by_id]
    if len(ordered) < 2:
        raise NotComparableError("Two applications from this opening are needed.")
    if any(a.evaluation is None for a in ordered):
        raise NotComparableError("Every candidate compared must have been examined.")

    criteria = sorted(opening.criteria, key=lambda c: c.position)
    rows = [_row(criterion, ordered) for criterion in criteria]

    return ComparisonOut(
        opening_title=opening.title,
        candidates=[
            ComparedCandidate(
                id=a.id,
                name=a.candidate.full_name,
                overall_score=a.evaluation.overall_score,  # type: ignore[union-attr]
                summary=a.evaluation.summary,  # type: ignore[union-attr]
                relevant_years_experience=a.evaluation.relevant_years_experience,  # type: ignore[union-attr]
                mandatory_requirements_met=a.evaluation.mandatory_requirements_met,  # type: ignore[union-attr]
                tampered=bool(a.integrity and str(a.integrity.verdict) != "clean"),
                decision=str(a.decision.kind) if a.decision else None,
            )
            for a in ordered
        ],
        criteria=rows,
        # The answer to "why is one ahead".
        decisive=_decisive(rows),
    )


def _decisive(rows: list[ComparedCriterion]) -> list[str]:
    """The smallest set of criteria that accounts for most of the gap.

    Naming a fixed two would be arbitrary: when the third row is worth nearly as
    much as the second, singling out the second is a claim the numbers do not
    support. So rows are taken largest first until they carry more than half the
    difference, which names one criterion when one criterion really is the story
    and three when the gap is genuinely spread out.
    """
    ranked = [r for r in sorted(rows, key=lambda r: -r.spread) if r.spread > 0]
    total = sum((r.spread for r in ranked), Decimal("0"))
    if total == 0:
        return []

    running = Decimal("0")
    named: list[str] = []
    for row in ranked:
        named.append(row.criterion_name)
        running += row.spread
        if running * 2 > total:
            break
    return named


def _row(criterion: Criterion, applications: list[Application]) -> ComparedCriterion:
    sides: list[SideEvidence] = []
    for application in applications:
        evaluation = application.evaluation
        assert evaluation is not None
        score = next((s for s in evaluation.scores if s.criterion_id == criterion.id), None)
        rating = score.score if score else 0
        sides.append(
            SideEvidence(
                application_id=application.id,
                score=rating,
                contribution=contribution(rating, criterion.weight),
                justification=score.justification if score else "",
                quotes=[
                    str(item.get("quote", ""))
                    for item in (score.evidence if score else [])
                    if item.get("found")
                ],
            )
        )

    scores = [s.score for s in sides]
    best = max(scores)
    return ComparedCriterion(
        criterion_id=criterion.id,
        criterion_name=criterion.name,
        weight=criterion.weight,
        mandatory=criterion.mandatory,
        sides=sides,
        # A tie leads nowhere, so nobody is marked ahead when everyone agrees.
        leaders=[s.application_id for s in sides if s.score == best]
        if len(set(scores)) > 1
        else [],
        spread=contribution(best, criterion.weight) - contribution(min(scores), criterion.weight),
    )
