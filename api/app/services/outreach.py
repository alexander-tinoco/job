"""Drafting and sending candidate emails."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Application, AuditLog, JobOpening, OutreachDraft
from app.db.types import DecisionKind, OpeningStatus, OutreachKind, OutreachState
from app.outreach import render, sender

logger = logging.getLogger(__name__)


class NotDecidedError(Exception):
    """Only a decided application gets an email."""


class AlreadySentError(Exception):
    """This message has already gone out."""


class OpeningStillOpenError(Exception):
    """Drafts are generated once the opening closes."""


def _sender_name(actor: str) -> str:
    return actor.split("@")[0].replace(".", " ").title() if "@" in actor else actor


def draft_for(session: Session, application: Application, actor: str) -> OutreachDraft:
    decision = application.decision
    if decision is None:
        raise NotDecidedError("This application has no decision yet.")
    if application.outreach is not None and application.outreach.state is OutreachState.SENT:
        raise AlreadySentError("An email has already been sent to this candidate.")

    kind = OutreachKind.INVITE if decision.kind is DecisionKind.SHORTLIST else OutreachKind.DECLINE
    rendered = render.render(
        kind,
        render.Merge(
            first_name=render.first_name(application.candidate.full_name),
            role=application.opening.title,
            company=application.opening.company.name,
            sender_name=_sender_name(actor),
        ),
    )

    existing: OutreachDraft | None = application.outreach
    if existing is not None:
        # Re-drafting replaces an untouched draft rather than piling up copies.
        existing.kind = kind
        existing.subject = rendered.subject
        existing.body = rendered.body
        existing.template_version = rendered.template_version
        existing.state = OutreachState.DRAFT
        session.flush()
        return existing

    draft = OutreachDraft(
        application=application,
        kind=kind,
        subject=rendered.subject,
        body=rendered.body,
        template_version=rendered.template_version,
    )
    session.add(draft)
    session.flush()
    return draft


def draft_all(session: Session, opening: JobOpening, actor: str) -> list[OutreachDraft]:
    """Draft for every decided candidate in a closed opening.

    Closed first, on purpose: drafting mid-round invites sending a decline to
    someone the round would have reconsidered.
    """
    if opening.status is not OpeningStatus.CLOSED:
        raise OpeningStillOpenError("Close the opening before drafting outreach.")

    applications = session.scalars(
        select(Application)
        .where(Application.job_opening_id == opening.id)
        .options(
            selectinload(Application.candidate),
            selectinload(Application.decision),
            selectinload(Application.outreach),
            selectinload(Application.opening).selectinload(JobOpening.company),
        )
    ).all()

    drafts: list[OutreachDraft] = []
    for application in applications:
        if application.decision is None:
            continue
        try:
            drafts.append(draft_for(session, application, actor))
        except AlreadySentError:
            continue
    return drafts


def send(session: Session, draft: OutreachDraft, actor: str) -> OutreachDraft:
    """Send one approved message. This is the only place anything leaves."""
    if draft.state is OutreachState.SENT:
        raise AlreadySentError("This message has already been sent.")

    recipient = draft.application.candidate.email
    try:
        delivery = sender.send(recipient, draft.subject, draft.body)
    except sender.SendFailedError as exc:
        draft.state = OutreachState.FAILED
        draft.last_error = str(exc)[:2000]
        session.flush()
        raise

    draft.state = OutreachState.SENT
    draft.approved_by = actor
    draft.sent_at = datetime.now(UTC)
    draft.provider_message_id = delivery.provider_message_id or None
    draft.last_error = None

    session.add(
        AuditLog(
            actor=actor,
            action=f"outreach.{draft.kind}",
            entity_type="application",
            entity_id=draft.application_id,
            # No recipient address and no body: the audit records that a person
            # approved a send, not the contents of someone's rejection (plan §8).
            payload={
                "template_version": draft.template_version,
                "provider_message_id": draft.provider_message_id,
            },
        )
    )
    session.flush()
    logger.info("outreach_sent application_id=%s kind=%s", draft.application_id, draft.kind)
    return draft


def for_opening(session: Session, opening_id: uuid.UUID) -> list[OutreachDraft]:
    return list(
        session.scalars(
            select(OutreachDraft)
            .join(Application, Application.id == OutreachDraft.application_id)
            .where(Application.job_opening_id == opening_id)
            .order_by(OutreachDraft.kind, OutreachDraft.created_at)
            .options(selectinload(OutreachDraft.application).selectinload(Application.candidate))
        )
    )
