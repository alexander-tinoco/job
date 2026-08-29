"""The commands that ship inside the image.

`app/cli.py` is the only interface a deployment has before there is a user to
sign in as, and it was at 0% — the operator's one tool, untested.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.db.models import ResumeDocument, User
from app.services import duplicates
from tests.factories import make_application, make_opening

RESUME_TEXT = "Ada Lovelace. Six years of Python and PostgreSQL, shipping billing systems. " * 6


@pytest.fixture
def cli_session(session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    """Point the commands at the test transaction.

    They open their own session against `DATABASE_URL`, which in a test run is
    the development database — the commands would otherwise write there.
    """
    monkeypatch.setattr(cli, "SessionLocal", lambda: _NoClose(session))
    return session


class _NoClose:
    """A context manager that hands over the test session and never closes it."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *_: object) -> None:
        pass


def _answers(monkeypatch: pytest.MonkeyPatch, *replies: str) -> None:
    remaining = list(replies)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: remaining.pop(0))


# --- create-user ---


def test_creating_the_first_user(
    cli_session: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _answers(monkeypatch, "correct-horse-battery", "correct-horse-battery")

    assert cli.main(["create-user", "Ada@Example.com", "Ada Lovelace"]) == 0

    user = cli_session.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    assert user.full_name == "Ada Lovelace"
    # Stored as a hash, never as what was typed.
    assert "correct-horse-battery" not in user.password_hash
    assert user.password_hash.startswith("$argon2")
    assert "Created ada@example.com" in capsys.readouterr().out


def test_the_password_is_prompted_never_taken_as_an_argument(
    cli_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A command line ends up in shell history and in the process list."""
    asked: list[str] = []
    monkeypatch.setattr(
        cli.getpass, "getpass", lambda prompt: asked.append(prompt) or "s3cret-phrase-ok"
    )

    cli.main(["create-user", "ada@example.com", "Ada Lovelace"])

    assert asked == ["Password: ", "Repeat: "]


def test_a_mistyped_repeat_creates_nobody(
    cli_session: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _answers(monkeypatch, "correct-horse-battery", "correct-horse-batteru")

    assert cli.main(["create-user", "ada@example.com", "Ada Lovelace"]) == 1
    assert cli_session.scalar(select(User).where(User.email == "ada@example.com")) is None
    assert "do not match" in capsys.readouterr().out


def test_a_weak_password_is_refused_with_the_reason(
    cli_session: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _answers(monkeypatch, "short", "short")

    assert cli.main(["create-user", "ada@example.com", "Ada Lovelace"]) == 1
    assert cli_session.scalar(select(User).where(User.email == "ada@example.com")) is None
    assert capsys.readouterr().out.strip()


def test_an_existing_email_is_not_overwritten(
    cli_session: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _answers(monkeypatch, "correct-horse-battery", "correct-horse-battery")
    cli.main(["create-user", "ada@example.com", "Ada Lovelace"])
    before = cli_session.scalar(select(User).where(User.email == "ada@example.com"))
    assert before is not None
    original = before.password_hash

    _answers(monkeypatch, "another-good-password", "another-good-password")
    assert cli.main(["create-user", "ADA@example.com", "Someone Else"]) == 1

    assert before.password_hash == original
    assert before.full_name == "Ada Lovelace"
    assert "already exists" in capsys.readouterr().out


def test_create_user_without_a_name_explains_itself(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["create-user", "ada@example.com"]) == 2
    assert "usage:" in capsys.readouterr().out


# --- backfill-fingerprints ---


def test_backfilling_fingerprints_from_the_command_line(
    cli_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    opening = make_opening(cli_session, slug="cli-backfill")
    application = make_application(cli_session, opening, "a@cli.com")
    application.resume = ResumeDocument(
        storage_path=f"{application.id}/cv.pdf",
        visible_text=RESUME_TEXT,
        total_text=RESUME_TEXT,
    )
    cli_session.flush()
    assert application.resume.text_digest is None

    assert cli.main(["backfill-fingerprints"]) == 0

    assert application.resume.text_digest == duplicates.digest(RESUME_TEXT)
    assert "Fingerprinted 1" in capsys.readouterr().out


def test_backfilling_twice_changes_nothing(
    cli_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["backfill-fingerprints"])
    capsys.readouterr()

    assert cli.main(["backfill-fingerprints"]) == 0
    assert "Fingerprinted 0" in capsys.readouterr().out


# --- the entry point ---


def test_an_unknown_command_lists_the_real_ones(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["evaluate-everything"]) == 2
    printed = capsys.readouterr().out
    assert "create-user" in printed
    assert "backfill-fingerprints" in printed


def test_no_command_at_all_lists_them_too(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2
    assert "usage:" in capsys.readouterr().out


def test_the_arguments_default_to_the_command_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["app.cli"])
    assert cli.main() == 2
    assert "usage:" in capsys.readouterr().out
