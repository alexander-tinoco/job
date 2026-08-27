from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import get_settings
from app.db import models  # noqa: F401  -- import registers every table on Base
from app.db.base import Base
from app.main import app

TEST_DB = "screening_test"
ADMIN_TOKEN = "test-admin-token"


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
def client(session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A client bound to the test transaction, with the admin guard configured."""
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    get_settings.cache_clear()

    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def auth() -> dict[str, str]:
    return {"X-Admin-Token": ADMIN_TOKEN}
