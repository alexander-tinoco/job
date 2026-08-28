"""Run the evaluation for one application and persist the result."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ai.client import MODEL_ID
from app.ai.evaluator import (
    PROMPT_VERSION,
    EvaluationRequest,
    RubricCriterion,
    evaluate,
)
from app.ai.schema import EvaluationOutput
from app.ai.verify import VerifiedEvaluation, verify
from app.db.models import Application, CriterionScore, Evaluation
from app.db.types import ApplicationState

logger = logging.getLogger(__name__)


class NotReadyError(Exception):
    """The application has no sanitized text to evaluate yet."""


def build_request(application: Application) -> EvaluationRequest:
    opening = application.opening
    resume = application.resume
    if resume is None or not resume.visible_text.strip():
        raise NotReadyError("No extracted résumé text to evaluate.")

    return EvaluationRequest(
        job_title=opening.title,
        company_context=opening.company_context,
        criteria=tuple(
            # Weights are deliberately absent: the model must not see them.
            RubricCriterion(
                name=criterion.name,
                description=criterion.description,
                mandatory=criterion.mandatory,
            )
            for criterion in sorted(opening.criteria, key=lambda c: c.position)
        ),
        # Only the visible text. The hidden text stays as evidence and never
        # reaches the model (plan §6, layer 1).
        resume_text=resume.visible_text,
    )


def evaluate_application(session: Session, application: Application) -> Evaluation:
    """Synchronous path: one AI call, then persist."""
    request = build_request(application)
    return persist_evaluation(session, application, evaluate(request))


def persist_evaluation(
    session: Session, application: Application, output: EvaluationOutput
) -> Evaluation:
    """Verify, score and store. Shared by the synchronous and batch paths.

    Everything that decides the ranking happens here, in Python: quotes are
    checked against the résumé and the weights produce the overall score (plan
    §6, layers 3 and 4). The batch path must not skip any of it.
    """
    resume = application.resume
    if resume is None:
        raise NotReadyError("No extracted résumé text to verify against.")
    # The sanitized text directly, not a rebuilt request: reconstructing the
    # whole prompt to recover a string it already has is wasted work.
    weights = {c.name: c.weight for c in application.opening.criteria}
    verified: VerifiedEvaluation = verify(output, resume.visible_text, weights)

    by_name = {c.name.strip().lower(): c for c in application.opening.criteria}
    evaluation = Evaluation(
        application=application,
        overall_score=verified.overall_score,
        relevant_years_experience=Decimal(str(output.relevant_years_experience)),
        mandatory_requirements_met=output.mandatory_requirements_met,
        missing_requirements=list(output.missing_requirements),
        risks=list(output.risks),
        review_flags=list(verified.review_reasons),
        detected_skills=list(output.detected_skills),
        summary=output.summary,
        needs_human_review=verified.needs_human_review,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        rubric_version=application.opening.rubric_version,
    )
    evaluation.scores = [
        CriterionScore(
            criterion_id=by_name[criterion.criterion_name.strip().lower()].id,
            score=criterion.score,
            justification=criterion.justification,
            evidence=[
                {"quote": q.quote, "found": q.found, "start": q.start, "end": q.end}
                for q in criterion.quotes
            ],
        )
        for criterion in verified.criteria
        if criterion.matched_rubric
    ]

    session.add(evaluation)
    application.state = ApplicationState.EVALUATED
    # No PII in logs: the application id is the only identifier (plan §8).
    logger.info(
        "evaluated application_id=%s score=%s review=%s",
        application.id,
        verified.overall_score,
        verified.needs_human_review,
    )
    return evaluation
