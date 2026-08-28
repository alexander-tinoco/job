"""Sign-in security.

Each test pins a property that an attacker would otherwise exercise.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE
from app.core.security import (
    WeakPasswordError,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from app.db.models import AuditLog, LoginAttempt, User
from app.db.models import Session as SessionRow
from app.services import auth
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


def _login(client: TestClient, email: str = TEST_EMAIL, password: str = TEST_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# --- Password storage ---


def test_passwords_are_hashed_with_argon2id_and_salted() -> None:
    first = hash_password("correct-horse-battery")
    second = hash_password("correct-horse-battery")

    assert first.startswith("$argon2id$")
    # Different salts, so identical passwords do not produce identical hashes
    # and a leaked table cannot be grouped by "who shares a password".
    assert first != second
    assert verify_password("correct-horse-battery", first)
    assert not verify_password("wrong", first)


def test_the_plaintext_password_is_never_stored(session: Session, user: User) -> None:
    assert TEST_PASSWORD not in user.password_hash


@pytest.mark.parametrize("password", ["", "short", "1234567"])
def test_short_passwords_are_refused(password: str) -> None:
    with pytest.raises(WeakPasswordError):
        hash_password(password)


def test_an_absurdly_long_password_is_refused() -> None:
    """Unbounded input turns a memory-hard hash into a denial of service."""
    with pytest.raises(WeakPasswordError):
        hash_password("x" * 5000)


# --- Session tokens ---


def test_the_session_token_is_stored_only_as_a_hash(
    client: TestClient, session: Session, user: User
) -> None:
    """A dump of this table must not hand anyone a working session."""
    _login(client)

    token = client.cookies.get(SESSION_COOKIE)
    assert token is not None
    row = session.scalar(select(SessionRow))
    assert row is not None
    assert row.token_hash != token
    assert row.token_hash == hash_session_token(token)


def test_session_tokens_are_unique_and_unguessable() -> None:
    tokens = {new_session_token() for _ in range(200)}

    assert len(tokens) == 200
    assert all(len(token) >= 40 for token in tokens)


def test_the_cookie_is_httponly_and_samesite_strict(client: TestClient, user: User) -> None:
    """HttpOnly is why the session is not in localStorage: a script cannot read it."""
    response = _login(client)

    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=strict" in header
    assert f"{SESSION_COOKIE}=" in header


def test_signing_in_again_mints_a_new_token(
    client: TestClient, session: Session, user: User
) -> None:
    """Session fixation: a value planted beforehand must not become authenticated."""
    _login(client)
    first = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    _login(client)
    second = client.cookies.get(SESSION_COOKIE)

    assert first != second
    assert len(list(session.scalars(select(SessionRow)))) == 2


# --- What failures reveal ---


def test_an_unknown_email_and_a_wrong_password_answer_identically(
    client: TestClient, user: User
) -> None:
    """Different answers would turn the login form into an account directory."""
    unknown = _login(client, email="nobody@example.com", password="whatever")
    wrong = _login(client, password="wrong-password")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]
    assert "Incorrect email or password" in unknown.json()["detail"]


def test_an_inactive_account_cannot_sign_in(
    client: TestClient, session: Session, user: User
) -> None:
    user.is_active = False
    session.flush()

    assert _login(client).status_code == 401


# --- Rate limiting ---


def test_repeated_failures_lock_the_account_out(
    client: TestClient, session: Session, user: User
) -> None:
    for _ in range(auth.MAX_FAILURES_PER_EMAIL):
        assert _login(client, password="wrong").status_code == 401

    blocked = _login(client, password="wrong")
    assert blocked.status_code == 429

    # And the lockout holds even once the password is right, so guessing the
    # password on the last attempt buys nothing.
    assert _login(client).status_code == 429


def test_a_successful_sign_in_clears_the_throttle(
    client: TestClient, session: Session, user: User
) -> None:
    for _ in range(auth.MAX_FAILURES_PER_EMAIL - 1):
        _login(client, password="wrong")
    assert session.scalar(select(LoginAttempt)) is not None

    assert _login(client).status_code == 200
    assert list(session.scalars(select(LoginAttempt))) == []


# --- Session lifetime ---


def test_an_expired_session_is_refused_and_revoked(
    client: TestClient, session: Session, user: User
) -> None:
    _login(client)
    row = session.scalar(select(SessionRow))
    assert row is not None
    row.expires_at = auth.now() - auth.ABSOLUTE_LIFETIME
    session.flush()

    assert client.get("/api/v1/openings").status_code == 401
    assert row.revoked_at is not None


def test_an_idle_session_is_refused(client: TestClient, session: Session, user: User) -> None:
    """Alive but untouched for too long is over, even before the absolute deadline."""
    _login(client)
    row = session.scalar(select(SessionRow))
    assert row is not None
    row.last_seen_at = auth.now() - auth.IDLE_TIMEOUT - auth.timedelta(minutes=1)
    session.flush()

    assert client.get("/api/v1/openings").status_code == 401


def test_activity_pushes_the_idle_deadline_forward(
    client: TestClient, session: Session, user: User
) -> None:
    _login(client)
    row = session.scalar(select(SessionRow))
    assert row is not None
    row.last_seen_at = auth.now() - auth.timedelta(hours=1)
    session.flush()
    before = row.last_seen_at

    client.get("/api/v1/openings")
    session.refresh(row)

    assert row.last_seen_at > before


def test_disabling_an_account_ends_its_live_sessions(
    client: TestClient, session: Session, user: User
) -> None:
    _login(client)
    user.is_active = False
    session.flush()

    assert client.get("/api/v1/openings").status_code == 401


# --- Logout ---


def test_logout_revokes_on_the_server_not_just_in_the_browser(
    client: TestClient, session: Session, user: User
) -> None:
    """Clearing the cookie alone leaves a working session for anyone who copied it."""
    _login(client)
    token = client.cookies.get(SESSION_COOKIE)
    assert token is not None

    assert client.post("/api/v1/auth/logout").status_code == 204

    row = session.scalar(select(SessionRow))
    assert row is not None and row.revoked_at is not None
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/api/v1/openings").status_code == 401


# --- Who is signed in ---


def test_me_reports_the_signed_in_user(client: TestClient, auth: dict[str, str]) -> None:
    body = client.get("/api/v1/auth/me").json()

    assert body["email"] == TEST_EMAIL
    assert "password_hash" not in body


def test_me_is_refused_when_anonymous(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


# --- Audit ---


def test_sign_in_and_sign_out_are_audited(client: TestClient, session: Session, user: User) -> None:
    _login(client)
    client.post("/api/v1/auth/logout")

    actions = [
        log.action for log in session.scalars(select(AuditLog).order_by(AuditLog.created_at))
    ]
    assert "auth.login" in actions
    assert "auth.logout" in actions
