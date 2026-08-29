import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Before anything imports the settings. `.env` sits at the repository root and
# is read by `Settings`, so without this the whole suite runs holding the real
# OpenAI key — which a failing assertion will happily print. No test may call
# the API anyway (CLAUDE.md AI rule 12), so the key has no business being here.
for _secret in ("OPENAI_API_KEY", "RESEND_API_KEY", "METRICS_TOKEN"):
    os.environ[_secret] = ""

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_session  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db import models  # noqa: F401, E402  -- registers every table on Base
from app.db.base import Base  # noqa: E402
from app.db.models import User  # noqa: E402
from app.main import app  # noqa: E402

TEST_DB = "screening_test"
TEST_EMAIL = "hr@example.com"
TEST_PASSWORD = "correct-horse-battery"


def _test_database_url() -> str:
    url = get_settings().database_url
    base, _, _ = url.rpartition("/")
    return f"{base}/{TEST_DB}"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """A disposable test database.

    Tests run against real Postgres, not SQLite: native enums, JSONB and the
    generated tsvector column do not exist in SQLite, so an in-memory database
    would let tests pass while production fails.
    """
    admin_url = _test_database_url().rpartition("/")[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()

    test_engine = create_engine(_test_database_url())
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()

    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session wrapped in a transaction that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    with Session(bind=connection, expire_on_commit=False) as db:
        yield db
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def client(
    session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[TestClient]:
    """A client bound to the test transaction, with the admin guard configured.

    Uploads go to a per-test tmp_path so a test can never write into the real
    uploads directory.
    """
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    # The test client speaks plain http, so the Secure flag would stop the
    # cookie ever being stored.
    monkeypatch.setenv("COOKIE_SECURE", "false")
    get_settings.cache_clear()

    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def user(session: Session) -> User:
    from app.services.auth import create_user

    created = create_user(session, TEST_EMAIL, "HR Person", TEST_PASSWORD)
    session.flush()
    return created


@pytest.fixture
def auth(client: TestClient, user: User) -> dict[str, str]:
    """Sign in for real and keep the cookie.

    Kept named `auth` and returning a dict so existing tests pass it unchanged;
    the cookie the client stored is what actually authenticates them.
    """
    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {}
