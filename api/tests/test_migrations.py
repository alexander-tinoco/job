"""Migrations must be reversible, not just applicable.

This exists because the same defect shipped twice: `autogenerate` creates native
enum types implicitly when it creates the tables that use them, and never emits
the matching DROP TYPE. `downgrade base` then leaves the types behind and the
next `upgrade head` fails with "type already exists".

It was fixed once in the initial migration, documented in the README, and
reintroduced in the next migration that added an enum. A note in a document did
not stop it; this test does.
"""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings

MIGRATION_DB = "screening_migrations"
API_ROOT = Path(__file__).resolve().parent.parent


def _admin_url() -> str:
    return get_settings().database_url.rpartition("/")[0] + "/postgres"


def _alembic(command: list[str], database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(API_ROOT / ".venv" / "bin" / "alembic"), *command],
        cwd=API_ROOT,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": database_url, "HOME": "/tmp"},
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture
def scratch_url() -> str:
    """A database of its own, so this never touches the test or dev schema."""
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{MIGRATION_DB}"'))
    admin.dispose()

    url = get_settings().database_url.rpartition("/")[0] + f"/{MIGRATION_DB}"
    yield url

    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}" WITH (FORCE)'))
    admin.dispose()


def test_upgrade_downgrade_upgrade_is_clean(scratch_url: str) -> None:
    """The exact sequence CI runs, and the one that caught this twice."""
    for command in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        result = _alembic(command, scratch_url)
        assert result.returncode == 0, f"{' '.join(command)} failed:\n{result.stderr[-1500:]}"


def test_downgrade_leaves_no_enum_types_behind(scratch_url: str) -> None:
    """The precise invariant. A surviving type is what breaks the next upgrade."""
    assert _alembic(["upgrade", "head"], scratch_url).returncode == 0
    assert _alembic(["downgrade", "base"], scratch_url).returncode == 0

    engine = create_engine(scratch_url)
    with engine.connect() as connection:
        leftover = (
            connection.execute(
                text("SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname")
            )
            .scalars()
            .all()
        )
    engine.dispose()

    assert leftover == [], (
        f"these enum types survived downgrade: {', '.join(leftover)}. "
        "Add an explicit DROP TYPE to the downgrade of the migration that created them."
    )


def test_the_models_match_the_migrations(scratch_url: str) -> None:
    """`alembic check` on a freshly migrated database: no drift, no forgotten revision."""
    assert _alembic(["upgrade", "head"], scratch_url).returncode == 0
    result = _alembic(["check"], scratch_url)

    assert result.returncode == 0, result.stdout + result.stderr
