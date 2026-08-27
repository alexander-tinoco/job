from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Application, Candidate, ResumeDocument
from app.db.types import ApplicationState, OpeningStatus
from tests.factories import make_opening
from tests.pdfs import make_resume, not_a_pdf, oversized_pdf

FORM = {"full_name": "Ada Lovelace", "email": "Ada@Example.com", "consent": "true"}


def _apply(client: TestClient, slug: str, content: bytes = b"", **overrides: object) -> object:
    data = {**FORM, **overrides}
    return client.post(
        f"/openings/{slug}/apply",
        data=data,
        files={"resume": ("cv.pdf", content or make_resume(), "application/pdf")},
    )


def test_a_valid_application_is_accepted(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    opening = make_opening(session, slug="intake-ok")
    session.commit()

    response = _apply(client, opening.slug)

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == ApplicationState.RECEIVED
    assert body["opening_title"] == "Backend Engineer"

    application = session.get(Application, body["application_id"])
    assert application is not None
    assert application.resume is not None
    stored = Path(get_settings().uploads_dir) / application.resume.storage_path
    assert stored.exists()
    assert stored.read_bytes().startswith(b"%PDF-")


def test_the_stored_filename_is_not_guessable(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="intake-name")
    session.commit()

    response = _apply(client, opening.slug)
    application_id = response.json()["application_id"]

    path = session.execute(select(ResumeDocument.storage_path)).scalar_one()
    directory, _, filename = path.partition("/")
    assert directory == application_id
    assert "cv" not in filename and "ada" not in filename.lower()
    assert len(filename.removesuffix(".pdf")) >= 20


def test_email_is_lowercased_so_one_person_is_one_candidate(
    client: TestClient, session: Session
) -> None:
    first = make_opening(session, slug="intake-a")
    second = make_opening(session, slug="intake-b")
    session.commit()

    _apply(client, first.slug, email="Ada@Example.com")
    _apply(client, second.slug, email="ada@example.com")

    candidates = list(session.scalars(select(Candidate)))
    assert len(candidates) == 1
    assert candidates[0].email == "ada@example.com"
    assert len(candidates[0].applications) == 2


def test_a_renamed_executable_is_rejected(client: TestClient, session: Session) -> None:
    """Content-Type says application/pdf; the magic number says otherwise."""
    opening = make_opening(session, slug="intake-exe")
    session.commit()

    response = _apply(client, opening.slug, content=not_a_pdf())

    assert response.status_code == 415
    assert "not a PDF" in response.text
    assert session.scalar(select(Application)) is None


def test_an_oversized_upload_is_rejected(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="intake-big")
    session.commit()

    response = _apply(client, opening.slug, content=oversized_pdf(11 * 1024 * 1024))

    assert response.status_code == 413
    assert "10 MB or smaller" in response.text


def test_a_rejected_upload_leaves_no_file_behind(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="intake-clean")
    session.commit()

    _apply(client, opening.slug, content=not_a_pdf())

    root = Path(get_settings().uploads_dir)
    leftovers = list(root.rglob("*.pdf")) if root.exists() else []
    assert leftovers == []


def test_without_consent_the_application_is_refused(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="intake-consent")
    session.commit()

    response = _apply(client, opening.slug, consent="false")

    assert response.status_code == 422
    assert "Consent" in response.text
    assert session.scalar(select(Application)) is None


def test_consent_timestamp_comes_from_the_server(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="intake-ts")
    session.commit()

    _apply(client, opening.slug, consented_at="1999-01-01T00:00:00Z")

    candidate = session.scalar(select(Candidate))
    assert candidate is not None
    assert candidate.consented_at.year >= 2026


def test_a_closed_opening_refuses_applications(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="intake-closed")
    opening.status = OpeningStatus.CLOSED
    session.commit()

    response = _apply(client, opening.slug)

    assert response.status_code == 409
    assert "no longer accepting" in response.text


def test_applying_twice_to_the_same_opening_is_refused(
    client: TestClient, session: Session
) -> None:
    opening = make_opening(session, slug="intake-twice")
    session.commit()

    assert _apply(client, opening.slug).status_code == 201
    second = _apply(client, opening.slug)

    assert second.status_code == 409
    assert "already applied" in second.text


def test_an_invalid_email_is_rejected(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="intake-email")
    session.commit()

    response = _apply(client, opening.slug, email="not-an-email")

    assert response.status_code == 422


def test_unknown_opening_is_a_404(client: TestClient) -> None:
    assert _apply(client, "does-not-exist").status_code == 404
