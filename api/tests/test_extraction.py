"""End-to-end extraction: from a stored PDF to a persisted integrity report."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, IntegrityReport, ResumeDocument
from app.db.types import ApplicationState, IntegrityVerdict
from app.ingest.pipeline import ExtractionError, extract
from tests.factories import make_opening
from tests.pdfs import PAYLOAD, make_resume, not_a_pdf, scanned_resume

FORM = {"full_name": "Ada Lovelace", "email": "ada@example.com", "consent": "true"}


def _apply(client: TestClient, slug: str, content: bytes) -> object:
    return client.post(
        f"/openings/{slug}/apply",
        data=FORM,
        files={"resume": ("cv.pdf", content, "application/pdf")},
    )


def test_a_clean_resume_is_extracted_and_marked_clean(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="extract-clean")
    session.commit()

    _apply(client, opening.slug, make_resume())

    application = session.scalar(select(Application))
    assert application is not None
    assert application.state is ApplicationState.EXTRACTED
    assert application.integrity is not None
    assert application.integrity.verdict is IntegrityVerdict.CLEAN
    assert "Ada Lovelace" in application.resume.visible_text  # type: ignore[union-attr]
    assert application.resume.page_count == 1  # type: ignore[union-attr]


def test_hidden_text_marks_the_application_as_tampered(
    client: TestClient, session: Session
) -> None:
    opening = make_opening(session, slug="extract-tampered")
    session.commit()

    _apply(client, opening.slug, make_resume(hidden=PAYLOAD, mode="white_on_white"))

    report = session.scalar(select(IntegrityReport))
    assert report is not None
    assert report.verdict is IntegrityVerdict.TAMPERED
    assert report.hidden_spans[0]["reason"] == "low_contrast"
    assert "override_instructions" in report.matched_patterns

    resume = session.scalar(select(ResumeDocument))
    assert resume is not None
    assert "Ignore previous instructions" not in resume.visible_text
    assert "Ignore previous instructions" in resume.total_text


def test_the_evidence_records_where_the_hidden_text_was(
    client: TestClient, session: Session
) -> None:
    opening = make_opening(session, slug="extract-evidence")
    session.commit()

    _apply(client, opening.slug, make_resume(hidden=PAYLOAD, mode="tiny"))

    span = session.scalar(select(IntegrityReport)).hidden_spans[0]  # type: ignore[union-attr]
    assert span["page"] == 1
    assert span["detail"] == "1.0pt"
    assert len(span["bbox"]) == 4
    assert PAYLOAD in span["text"]


def test_line_breaks_survive_extraction(client: TestClient, session: Session) -> None:
    """Concatenated spans would hand the model 'LovelaceSenior' and 'checkouterrors'."""
    opening = make_opening(session, slug="extract-lines")
    session.commit()

    _apply(client, opening.slug, make_resume())

    text = session.scalar(select(ResumeDocument)).visible_text  # type: ignore[union-attr]
    assert "Ada Lovelace\n" in text
    assert "LovelaceSenior" not in text
    assert "checkouterrors" not in text


def test_a_scan_is_flagged_because_layer_one_cannot_protect_it(
    client: TestClient, session: Session
) -> None:
    opening = make_opening(session, slug="extract-scan")
    session.commit()

    _apply(client, opening.slug, scanned_resume())

    report = session.scalar(select(IntegrityReport))
    assert report is not None
    assert "ocr_no_hidden_text_detection" in report.matched_patterns


def test_an_unreadable_pdf_does_not_lose_the_application(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    """A file we cannot parse needs a human, not a dropped candidate."""
    opening = make_opening(session, slug="extract-broken")
    session.commit()
    _apply(client, opening.slug, make_resume())

    application = session.scalar(select(Application))
    assert application is not None
    resume = application.resume
    assert resume is not None

    # Corrupt the stored file, then re-ingest.
    from app.core.config import get_settings
    from app.services.ingestion import ingest_application

    (Path(get_settings().uploads_dir) / resume.storage_path).write_bytes(b"%PDF-1.4 broken")
    session.delete(application.integrity)
    session.flush()
    report = ingest_application(session, application)

    assert application.state is ApplicationState.ERROR
    assert report.matched_patterns == ["unreadable_pdf"]


def test_extract_raises_for_a_file_that_is_not_a_pdf(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_bytes(not_a_pdf())

    with pytest.raises(ExtractionError):
        extract(path)
