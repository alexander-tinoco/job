"""Signing in, staying signed in, and signing out."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app.core.security import (
    hash_password,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password,
    waste_time_like_a_verification,
)
from app.db.models import AuditLog, LoginAttempt, Session, User

# A session ends at the earlier of the two: long enough away and it is gone,
# long enough alive and it is gone regardless of activity.
IDLE_TIMEOUT = timedelta(hours=8)
ABSOLUTE_LIFETIME = timedelta(hours=24)

# Throttling. Per email so one account cannot be hammered, and per address so one
# source cannot sweep many accounts.
LOCKOUT_WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_IP = 20


class AuthError(Exception):
    """Sign-in failed. The message is deliberately the same for every cause."""


class RateLimitedError(AuthError):
    pass


@dataclass(frozen=True)
class Issued:
    token: str
    session: Session


def now() -> datetime:
    return datetime.now(UTC)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def create_user(session: DbSession, email: str, full_name: str, password: str) -> User:
    user = User(
        email=normalise_email(email),
        full_name=full_name.strip(),
        password_hash=hash_password(password),
    )
    session.add(user)
    session.flush()
    return user


def _recent_failures(session: DbSession, email: str, source_ip: str) -> tuple[int, int]:
    since = now() - LOCKOUT_WINDOW
    by_email = int(
        session.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.email == email, LoginAttempt.created_at >= since)
        )
        or 0
    )
    by_ip = int(
        session.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.source_ip == source_ip, LoginAttempt.created_at >= since)
        )
        or 0
    )
    return by_email, by_ip


def authenticate(
    session: DbSession, email: str, password: str, source_ip: str, user_agent: str = ""
) -> Issued:
    """Verify credentials and open a session.

    Every failure raises the same message. Telling a caller that the email was
    unknown turns the login form into a way to find out who has an account.
    """
    address = normalise_email(email)
    by_email, by_ip = _recent_failures(session, address, source_ip)
    if by_email >= MAX_FAILURES_PER_EMAIL or by_ip >= MAX_FAILURES_PER_IP:
        raise RateLimitedError("Too many attempts. Try again in a few minutes.")

    user = session.scalar(select(User).where(User.email == address))
    if user is None:
        # Spend the same time as a real verification would, or the response time
        # itself answers "does this email exist?".
        waste_time_like_a_verification()
        _record_failure(session, address, source_ip)
        raise AuthError("Incorrect email or password.")

    if not verify_password(password, user.password_hash) or not user.is_active:
        _record_failure(session, address, source_ip)
        raise AuthError("Incorrect email or password.")

    if needs_rehash(user.password_hash):
        # Parameters were raised since this password was set; upgrade it now
        # that we hold the plaintext for a moment.
        user.password_hash = hash_password(password)

    # Clear the throttle for this account: a correct password proves it is not
    # an attack in progress.
    session.execute(delete(LoginAttempt).where(LoginAttempt.email == address))

    issued = open_session(session, user, user_agent)
    user.last_login_at = now()
    session.add(
        AuditLog(
            actor=user.email,
            action="auth.login",
            entity_type="user",
            entity_id=user.id,
            payload={"user_agent": user_agent[:200]},
        )
    )
    session.flush()
    return issued


def _record_failure(session: DbSession, email: str, source_ip: str) -> None:
    session.add(LoginAttempt(email=email, source_ip=source_ip))
    session.flush()


def open_session(session: DbSession, user: User, user_agent: str = "") -> Issued:
    """Mint a fresh session. Called only on a successful sign-in.

    A new token every time is what stops session fixation: a value an attacker
    planted before the sign-in is not the value that ends up authenticated.
    """
    token = new_session_token()
    moment = now()
    record = Session(
        user=user,
        token_hash=hash_session_token(token),
        expires_at=moment + ABSOLUTE_LIFETIME,
        last_seen_at=moment,
    )
    session.add(record)
    session.flush()
    return Issued(token=token, session=record)


def resolve_session(session: DbSession, token: str) -> User | None:
    """Return the signed-in user, or None if the session is not usable.

    Also pushes the idle deadline forward, which is why this is the only place
    allowed to read a session.
    """
    record = session.scalar(select(Session).where(Session.token_hash == hash_session_token(token)))
    if record is None or record.revoked_at is not None:
        return None

    moment = now()
    if record.expires_at <= moment or record.last_seen_at + IDLE_TIMEOUT <= moment:
        record.revoked_at = moment
        session.flush()
        return None

    if not record.user.is_active:
        record.revoked_at = moment
        session.flush()
        return None

    record.last_seen_at = moment
    session.flush()
    return record.user


def revoke(session: DbSession, token: str) -> None:
    record = session.scalar(select(Session).where(Session.token_hash == hash_session_token(token)))
    if record is None or record.revoked_at is not None:
        return
    record.revoked_at = now()
    session.add(
        AuditLog(
            actor=record.user.email,
            action="auth.logout",
            entity_type="user",
            entity_id=record.user_id,
            payload={},
        )
    )
    session.flush()


def revoke_all_for(session: DbSession, user: User) -> int:
    """End every session a user has. Used when an account is disabled."""
    moment = now()
    live = list(
        session.scalars(
            select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
        )
    )
    for record in live:
        record.revoked_at = moment
    session.flush()
    return len(live)
