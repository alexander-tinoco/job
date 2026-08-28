"""Retention, access and erasure.

The three things a candidate is owed and a client will be asked about. None of
them is optional: "deleted after six months" is a claim on the application page,
and a claim the code has to make true.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Application,
    AuditLog,
    Candidate,
    JobOpening,
    OutreachDraft,
    ResumeDocument,
)
from app.db.types import OpeningStatus
from app.services import storage

logger = logging.getLogger(__name__)

RETENTION = timedelta(days=183)


def now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Swept:
    applications: int = 0
    files_deleted: int = 0
    files_missing: int = 0
    openings: list[str] = field(default_factory=list)


def due_for_deletion(session: Session, at: datetime | None = None) -> list[Application]:
    """Applications to openings that closed more than the retention window ago.

    Measured from the opening closing rather than from the application arriving:
    a candidate who applied on day one and one who applied on the last day are
    part of the same round and are kept for the same period.
    """
    cutoff = (at or now()) - RETENTION
    return list(
        session.scalars(
            select(Application)
            .join(JobOpening, JobOpening.id == Application.job_opening_id)
            .where(
                JobOpening.status == OpeningStatus.CLOSED,
                JobOpening.updated_at < cutoff,
            )
            .options(selectinload(Application.resume))
        )
    )


def sweep(session: Session, at: datetime | None = None) -> Swept:
    """Delete what is past its retention. Files first, then rows.

    Files first because a row without its file is a recoverable inconsistency,
    while a file without its row is personal data nobody can find or delete.
    """
    swept = Swept()
    for application in due_for_deletion(session, at):
        resume = application.resume
        if resume is not None:
            if storage.delete_resume(resume.storage_path):
                swept.files_deleted += 1
            else:
                swept.files_missing += 1
        session.delete(application)
        swept.applications += 1

    if swept.applications:
        session.add(
            AuditLog(
                actor="system.retention",
                action="retention.sweep",
                entity_type="system",
                entity_id=_zero_uuid(),
                payload={
                    "applications": swept.applications,
                    "files_deleted": swept.files_deleted,
                    "files_missing": swept.files_missing,
                    "retention_days": RETENTION.days,
                },
            )
        )
    session.flush()
    logger.info("retention_sweep applications=%s files=%s", swept.applications, swept.files_deleted)
    return swept


def export_for(session: Session, email: str) -> dict[str, object] | None:
    """Everything held about one person, for a subject access request."""
    address = email.strip().lower()
    candidate = session.scalar(
        select(Candidate)
        .where(Candidate.email == address)
        .options(
            selectinload(Candidate.applications).selectinload(Application.resume),
            selectinload(Candidate.applications).selectinload(Application.evaluation),
            selectinload(Candidate.applications).selectinload(Application.integrity),
            selectinload(Candidate.applications).selectinload(Application.decision),
            selectinload(Candidate.applications).selectinload(Application.opening),
        )
    )
    if candidate is None:
        return None

    return {
        "candidate": {
            "full_name": candidate.full_name,
            "email": candidate.email,
            "phone": candidate.phone,
            "linkedin_url": candidate.linkedin_url,
            "consented_at": candidate.consented_at.isoformat(),
        },
        "applications": [
            {
                "opening": application.opening.title,
                "applied_at": application.created_at.isoformat(),
                "state": str(application.state),
                # The text we extracted, which is what was assessed. Included
                # because "what did you hold about me" has to mean it.
                "resume_text": application.resume.visible_text if application.resume else None,
                "evaluation": (
                    {
                        "overall_score": float(application.evaluation.overall_score),
                        "summary": application.evaluation.summary,
                        "model_id": application.evaluation.model_id,
                        "rubric_version": application.evaluation.rubric_version,
                    }
                    if application.evaluation
                    else None
                ),
                "integrity": (
                    str(application.integrity.verdict) if application.integrity else None
                ),
                "decision": (
                    {
                        "kind": str(application.decision.kind),
                        "reason": application.decision.reason,
                    }
                    if application.decision
                    else None
                ),
            }
            for application in candidate.applications
        ],
    }


@dataclass
class Erased:
    applications: int = 0
    files_deleted: int = 0


def erase(session: Session, email: str, actor: str) -> Erased | None:
    """Delete everything about one person, keeping the audit anonymous.

    The audit records survive with the candidate's identifier removed. Deleting
    them too would erase the evidence that a human made each decision, which is
    the record the same regulation requires us to keep.
    """
    address = email.strip().lower()
    candidate = session.scalar(
        select(Candidate)
        .where(Candidate.email == address)
        .options(selectinload(Candidate.applications).selectinload(Application.resume))
    )
    if candidate is None:
        return None

    erased = Erased()
    application_ids = [application.id for application in candidate.applications]
    for application in candidate.applications:
        if application.resume is not None and storage.delete_resume(
            application.resume.storage_path
        ):
            erased.files_deleted += 1
        erased.applications += 1

    # Outreach carries a subject line with the person's role; it goes too.
    for draft in session.scalars(
        select(OutreachDraft).where(OutreachDraft.application_id.in_(application_ids))
    ):
        session.delete(draft)

    session.delete(candidate)  # Cascades to applications, résumés, evaluations.

    for log in session.scalars(select(AuditLog).where(AuditLog.entity_id.in_(application_ids))):
        log.actor = "erased"
        log.payload = {**log.payload, "erased": True}

    session.add(
        AuditLog(
            actor=actor,
            action="lifecycle.erase",
            entity_type="candidate",
            entity_id=_zero_uuid(),
            # No email: recording who asked to be forgotten alongside the fact
            # that they were forgotten would defeat the exercise.
            payload={"applications": erased.applications, "files": erased.files_deleted},
        )
    )
    session.flush()
    logger.info("erasure applications=%s files=%s", erased.applications, erased.files_deleted)
    return erased


def _zero_uuid() -> object:
    import uuid

    return uuid.UUID(int=0)


def resume_documents(session: Session) -> list[ResumeDocument]:
    return list(session.scalars(select(ResumeDocument)))
