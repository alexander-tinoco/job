"""Retention, subject access, erasure and export.

These are the promises the application page makes to a candidate. Each one is
tested against what actually happens on disk and in the database, not against
the intention.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Application, AuditLog, Candidate, ResumeDocument
from app.db.types import DecisionKind, OpeningStatus
from app.services import lifecycle
from tests.factories import make_opening
from tests.pdfs import make_resume


def _applied(client: TestClient, slug: str, email: str, name: str = "Ada Lovelace") -> None:
    client.post(
        f"/openings/{slug}/apply",
        data={"full_name": name, "email": email, "consent": "true"},
        files={"resume": ("cv.pdf", make_resume(), "application/pdf")},
    )


def _stored_path(session: Session) -> Path:
    resume = session.scalar(select(ResumeDocument))
    assert resume is not None
    return Path(get_settings().uploads_dir) / resume.storage_path


# --- Retention ---


def test_an_open_opening_is_never_swept(client: TestClient, session: Session) -> None:
    make_opening(session, slug="life-open")
    session.commit()
    _applied(client, "life-open", "open@example.com")

    swept = lifecycle.sweep(session, at=datetime.now(UTC) + timedelta(days=3650))

    assert swept.applications == 0
    assert session.scalar(select(Application)) is not None


def test_a_recently_closed_opening_is_not_swept(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="life-recent")
    session.commit()
    _applied(client, "life-recent", "recent@example.com")
    opening.status = OpeningStatus.CLOSED
    session.flush()

    assert lifecycle.sweep(session).applications == 0


def test_past_the_window_the_application_and_its_file_are_deleted(
    client: TestClient, session: Session
) -> None:
    """ "Deleted six months after the opening closes" has to be true."""
    opening = make_opening(session, slug="life-old")
    session.commit()
    _applied(client, "life-old", "old@example.com")
    opening.status = OpeningStatus.CLOSED
    session.flush()
    path = _stored_path(session)
    assert path.exists()

    swept = lifecycle.sweep(session, at=datetime.now(UTC) + lifecycle.RETENTION + timedelta(days=1))

    assert swept.applications == 1
    assert swept.files_deleted == 1
    assert not path.exists(), "a file without its row is data nobody can find or delete"
    assert session.scalar(select(Application)) is None


def test_a_sweep_records_itself(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="life-audit")
    session.commit()
    _applied(client, "life-audit", "audit@example.com")
    opening.status = OpeningStatus.CLOSED
    session.flush()

    lifecycle.sweep(session, at=datetime.now(UTC) + lifecycle.RETENTION + timedelta(days=1))

    log = session.scalar(select(AuditLog).where(AuditLog.action == "retention.sweep"))
    assert log is not None
    assert log.payload["applications"] == 1
    assert log.payload["retention_days"] == lifecycle.RETENTION.days


# --- Subject access ---


def test_access_returns_what_is_actually_held(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    make_opening(session, slug="life-access")
    session.commit()
    _applied(client, "life-access", "access@example.com")

    body = client.get("/api/v1/data-subject/access@example.com").json()

    assert body["candidate"]["email"] == "access@example.com"
    assert body["candidate"]["consented_at"]
    assert len(body["applications"]) == 1
    # "What do you hold about me" has to include the text that was assessed.
    assert "Ada Lovelace" in body["applications"][0]["resume_text"]


def test_access_is_case_insensitive(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    make_opening(session, slug="life-case")
    session.commit()
    _applied(client, "life-case", "case@example.com")

    assert client.get("/api/v1/data-subject/CASE@Example.com").status_code == 200


def test_access_to_an_unknown_address_is_a_404(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/v1/data-subject/nobody@example.com").status_code == 404


# --- Erasure ---


def test_erasure_removes_the_person_the_rows_and_the_file(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    make_opening(session, slug="life-erase")
    session.commit()
    _applied(client, "life-erase", "erase@example.com")
    path = _stored_path(session)
    assert path.exists()

    response = client.post("/api/v1/data-subject/erase", json={"email": "erase@example.com"})

    assert response.status_code == 200
    assert response.json()["files_deleted"] == 1
    assert not path.exists()
    assert session.scalar(select(Candidate)) is None
    assert session.scalar(select(Application)) is None


def test_erasure_keeps_the_audit_but_anonymises_it(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Deleting the audit too would erase the proof that a person decided."""
    from app.db.models import HumanDecision

    make_opening(session, slug="life-anon")
    session.commit()
    _applied(client, "life-anon", "anon@example.com")
    application = session.scalar(select(Application))
    assert application is not None
    application.decision = HumanDecision(
        kind=DecisionKind.REJECT, reason="No fit", decided_by="hr@acme.com"
    )
    session.add(
        AuditLog(
            actor="hr@acme.com",
            action="decision.reject",
            entity_type="application",
            entity_id=application.id,
            payload={"reason": "No fit"},
        )
    )
    session.commit()

    client.post("/api/v1/data-subject/erase", json={"email": "anon@example.com"})

    decision_log = session.scalar(select(AuditLog).where(AuditLog.action == "decision.reject"))
    assert decision_log is not None, "the record that a human decided must survive"
    assert decision_log.actor == "erased"
    assert decision_log.payload["erased"] is True


def test_the_erasure_record_does_not_name_the_person(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Recording who asked to be forgotten would defeat the exercise."""
    make_opening(session, slug="life-noname")
    session.commit()
    _applied(client, "life-noname", "forgetme@example.com")

    client.post("/api/v1/data-subject/erase", json={"email": "forgetme@example.com"})

    log = session.scalar(select(AuditLog).where(AuditLog.action == "lifecycle.erase"))
    assert log is not None
    assert "forgetme@example.com" not in str(log.payload)


def test_erasing_an_unknown_address_is_a_404(client: TestClient, auth: dict[str, str]) -> None:
    assert (
        client.post("/api/v1/data-subject/erase", json={"email": "nobody@example.com"}).status_code
        == 404
    )


# --- Export ---


def test_the_export_is_csv_with_a_header_and_a_row_per_candidate(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="life-csv")
    session.commit()
    _applied(client, "life-csv", "csv1@example.com")
    _applied(client, "life-csv", "csv2@example.com", name="Grace Hopper")

    response = client.get(f"/api/v1/openings/{opening.id}/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("rank,candidate,email,score")
    assert len(lines) == 3


def test_a_formula_in_a_name_is_neutralised(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """A candidate chooses their own name, and a spreadsheet will run it."""
    opening = make_opening(session, slug="life-formula")
    session.commit()
    _applied(client, "life-formula", "formula@example.com", name="=cmd|'/c calc'!A1")

    body = client.get(f"/api/v1/openings/{opening.id}/export.csv").text

    assert "=cmd" not in body.replace("'=cmd", "")
    assert "'=cmd" in body


def test_the_audit_trail_is_readable(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    make_opening(session, slug="life-trail")
    session.commit()

    body = client.get("/api/v1/audit").json()

    # Signing in is itself audited, so the trail is never empty for a user.
    assert any(entry["action"] == "auth.login" for entry in body)


def test_every_lifecycle_endpoint_requires_a_session(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="life-auth")
    session.commit()

    assert client.get("/api/v1/audit").status_code == 401
    assert client.get(f"/api/v1/openings/{opening.id}/export.csv").status_code == 401
    assert client.get("/api/v1/data-subject/a@b.com").status_code == 401
    assert client.post("/api/v1/data-subject/erase", json={"email": "a@b.com"}).status_code == 401
    assert client.post("/api/v1/retention/sweep").status_code == 401
