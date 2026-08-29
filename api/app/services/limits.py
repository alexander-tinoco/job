"""Throttling for the endpoints a stranger can reach.

Sign-in has had a limiter since the beginning; the public application form has
not, and it is the more expensive of the two. `POST /openings/{slug}/apply`
takes no session — the slug is the invitation — and does real work for every
call: it stores a file of up to 10 MB, runs PyMuPDF over it, and writes a queue
row that becomes a paid model call.

What this can and cannot prevent: by the time the endpoint runs, the upload has
already crossed the wire into a spooled temp file, so the bandwidth is spent
either way. Refusing here stops the disk write, the extraction and the model
call, which is where the cost actually is.

Counted per accepted application, not per attempt. Counting refusals would let a
blocked caller extend their own lockout forever by continuing to knock.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import LoginAttempt, RateEvent

WINDOW = timedelta(hours=1)

# Deliberately loose. The failure that matters is a real candidate turned away,
# and that failure is invisible to us — they simply do not apply. A flood is
# obvious in the numbers; a blocked applicant is not. Both are starting points
# to revisit against real traffic.
MAX_APPLICATIONS_PER_EMAIL = 5
# A shared office, a university or a careers fair all leave through one address,
# so this sits far above what one person could plausibly need.
MAX_APPLICATIONS_PER_IP = 20

APPLY_EMAIL = "apply_email"
APPLY_IP = "apply_ip"

# Long enough to outlive any window, short enough that neither throttle table
# becomes a standing record of who applied from where.
RETENTION = timedelta(days=2)


class RateLimitedError(Exception):
    """Too many of these, too quickly."""


def now() -> datetime:
    return datetime.now(UTC)


def fingerprint(email: str) -> str:
    """Equality without keeping the address.

    A digest answers "the same applicant again?", which is the only question a
    throttle asks, and leaves a dump of this table useless to anyone.
    """
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _count(session: Session, scope: str, key: str) -> int:
    since = now() - WINDOW
    return int(
        session.scalar(
            select(func.count())
            .select_from(RateEvent)
            .where(RateEvent.scope == scope, RateEvent.key == key, RateEvent.created_at >= since)
        )
        or 0
    )


def check_application(session: Session, email: str, source_ip: str) -> None:
    """Raise if this applicant or this address has sent too many recently."""
    if _count(session, APPLY_EMAIL, fingerprint(email)) >= MAX_APPLICATIONS_PER_EMAIL:
        raise RateLimitedError("You have sent several applications recently. Try again later.")
    if _count(session, APPLY_IP, source_ip) >= MAX_APPLICATIONS_PER_IP:
        raise RateLimitedError("Too many applications from this network. Try again later.")


def record_application(session: Session, email: str, source_ip: str) -> None:
    session.add(RateEvent(scope=APPLY_EMAIL, key=fingerprint(email)))
    session.add(RateEvent(scope=APPLY_IP, key=source_ip[:64]))
    session.flush()


def sweep(session: Session, at: datetime | None = None) -> int:
    """Drop throttle rows past their usefulness. Returns how many.

    Covers `login_attempts` as well, which had no sweep of its own and so grew
    without bound — a table of email addresses kept forever to enforce a fifteen
    minute lockout.
    """
    cutoff = (at or now()) - RETENTION
    removed = 0
    for model in (RateEvent, LoginAttempt):
        removed += int(
            session.scalar(select(func.count()).select_from(model).where(model.created_at < cutoff))
            or 0
        )
        session.execute(delete(model).where(model.created_at < cutoff))
    session.flush()
    return removed
