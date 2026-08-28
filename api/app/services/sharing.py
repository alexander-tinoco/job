"""Read-only links for people without an account.

Whoever screens is rarely whoever decides. This is the difference between one
user and three, and it costs the hiring manager nothing to use.

**The token is the credential here.** Unlike the panel's URL — which is only
kept out of sight — this link grants access on its own, so it is 256 bits of
randomness, stored only as a hash, time-limited and revocable.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Application, AuditLog, Evaluation, JobOpening, ShareLink
from app.db.types import DecisionKind, ShareScope

logger = logging.getLogger(__name__)

DEFAULT_LIFETIME = timedelta(days=14)
MAX_LIFETIME = timedelta(days=90)
TOKEN_BYTES = 32


class LinkNotUsableError(Exception):
    """Expired, revoked, or never existed. The caller is told no more than that."""


@dataclass(frozen=True)
class Issued:
    token: str
    link: ShareLink


def now() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    """SHA-256, not Argon2.

    The token is 256 bits of randomness, so there is nothing to brute-force and
    a slow hash on every page view would buy nothing. The point is only that a
    database dump yields no working links.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create(
    session: Session,
    opening: JobOpening,
    created_by: str,
    scope: ShareScope = ShareScope.SHORTLIST,
    label: str = "",
    lifetime: timedelta | None = None,
) -> Issued:
    window = min(lifetime or DEFAULT_LIFETIME, MAX_LIFETIME)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    link = ShareLink(
        job_opening_id=opening.id,
        token_hash=hash_token(token),
        scope=scope,
        label=label.strip(),
        created_by=created_by,
        expires_at=now() + window,
    )
    session.add(link)
    session.add(
        AuditLog(
            actor=created_by,
            action="share.create",
            entity_type="opening",
            entity_id=opening.id,
            # No token, not even a prefix: an audit row that leaks a credential
            # is worse than no audit row.
            payload={"scope": str(scope), "expires_at": link.expires_at.isoformat()},
        )
    )
    session.flush()
    logger.info("share_created opening_id=%s scope=%s", opening.id, scope)
    return Issued(token=token, link=link)


def revoke(session: Session, link: ShareLink, actor: str) -> None:
    if link.revoked_at is not None:
        return
    link.revoked_at = now()
    session.add(
        AuditLog(
            actor=actor,
            action="share.revoke",
            entity_type="opening",
            entity_id=link.job_opening_id,
            payload={"views": link.view_count},
        )
    )
    session.flush()


def for_opening(session: Session, opening_id: uuid.UUID) -> list[ShareLink]:
    return list(
        session.scalars(
            select(ShareLink)
            .where(ShareLink.job_opening_id == opening_id)
            .order_by(ShareLink.created_at.desc())
        )
    )


def resolve(session: Session, token: str) -> ShareLink:
    """Look a token up and count the view. Raises for anything unusable."""
    link = session.scalar(select(ShareLink).where(ShareLink.token_hash == hash_token(token)))
    if link is None or link.revoked_at is not None or link.expires_at <= now():
        # One message for every cause: distinguishing "expired" from "never
        # existed" tells a guesser they found something real.
        raise LinkNotUsableError("This link is not available.")

    link.view_count += 1
    link.last_viewed_at = now()
    session.flush()
    return link


def visible_applications(session: Session, link: ShareLink) -> list[Application]:
    """What the link is allowed to show.

    A shortlist link shows shortlisted candidates only. Nobody outside the
    company should see the people who were declined, and no share link shows an
    undecided candidate at all: a half-finished screen is not something to
    circulate.
    """
    query = (
        select(Application)
        .join(Evaluation, Evaluation.application_id == Application.id)
        .where(Application.job_opening_id == link.job_opening_id)
        .order_by(Evaluation.overall_score.desc())
        .options(
            selectinload(Application.candidate),
            selectinload(Application.resume),
            selectinload(Application.decision),
            selectinload(Application.integrity),
            selectinload(Application.evaluation).selectinload(Evaluation.scores),
        )
    )
    applications = list(session.scalars(query))

    if link.scope is ShareScope.SHORTLIST:
        return [
            a
            for a in applications
            if a.decision is not None and a.decision.kind is DecisionKind.SHORTLIST
        ]
    return applications
