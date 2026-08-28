"""Recording what a person decided, and why.

The decision never overwrites the model's evaluation: they coexist. That
disagreement is the most valuable data the product generates (plan §5), and it
is also the evidence that a human made the call — which is what keeps this out
of GDPR art. 22 territory (plan §8).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Application, AuditLog, HumanDecision
from app.schemas.panel import DecisionIn


class AlreadyDecidedError(Exception):
    """This application already carries a decision."""


def decide(session: Session, application: Application, payload: DecisionIn) -> HumanDecision:
    if application.decision is not None:
        raise AlreadyDecidedError("This application has already been decided.")

    decision = HumanDecision(
        application=application,
        kind=payload.kind,
        reason=payload.reason,
        decided_by=payload.decided_by,
    )
    session.add(decision)

    evaluation = application.evaluation
    session.add(
        AuditLog(
            actor=payload.decided_by,
            action=f"decision.{payload.kind}",
            entity_type="application",
            entity_id=application.id,
            # No PII: the reason is the operator's own words, and the score is
            # what the disagreement is measured against (plan §8).
            payload={
                "reason": payload.reason,
                "model_score": float(evaluation.overall_score) if evaluation else None,
                "model_id": evaluation.model_id if evaluation else None,
                "rubric_version": evaluation.rubric_version if evaluation else None,
            },
        )
    )
    session.flush()
    return decision
