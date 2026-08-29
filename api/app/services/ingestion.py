"""Persist the result of extraction against an application."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Application, IntegrityReport, ResumeDocument
from app.db.types import ApplicationState, IntegrityVerdict
from app.ingest.pipeline import ExtractionError, ExtractionResult, extract
from app.services.duplicates import fingerprint
from app.services.queue import enqueue

logger = logging.getLogger(__name__)

# Hidden text long enough to carry an instruction. Below this it is usually a
# stray glyph or a rendering artefact rather than an attack.
TAMPERING_CHAR_THRESHOLD = 25


def decide_verdict(result: ExtractionResult) -> IntegrityVerdict:
    """Hidden text is the strong signal; a pattern match on its own is weak.

    Patterns alone stay `suspicious` because the phrase may be innocent — a
    résumé that mentions "ideal candidate" in a cover letter is not an attack.
    """
    if result.hidden_char_count >= TAMPERING_CHAR_THRESHOLD:
        return IntegrityVerdict.TAMPERED
    if result.matched_patterns or result.hidden_spans:
        return IntegrityVerdict.SUSPICIOUS
    return IntegrityVerdict.CLEAN


def ingest_application(session: Session, application: Application) -> IntegrityReport:
    """Extract, sanitize and record. Never raises for a bad PDF.

    A file we cannot read is an application that needs a human, not a request
    that failed: the candidate has already submitted and should not be dropped.
    """
    resume: ResumeDocument | None = application.resume
    if resume is None:
        raise ValueError("Application has no résumé to ingest.")

    path = Path(get_settings().uploads_dir) / resume.storage_path
    try:
        result = extract(path)
    except ExtractionError as exc:
        # No PII in logs: the application id is the only identifier (plan §8).
        logger.warning("extraction_failed application_id=%s reason=%s", application.id, exc)
        application.state = ApplicationState.ERROR
        report = IntegrityReport(
            application=application,
            verdict=IntegrityVerdict.SUSPICIOUS,
            hidden_spans=[],
            matched_patterns=["unreadable_pdf"],
        )
        session.add(report)
        return report

    resume.visible_text = result.visible_text
    resume.total_text = result.total_text
    resume.page_count = result.page_count
    fingerprint(resume)

    report = IntegrityReport(
        application=application,
        verdict=decide_verdict(result),
        hidden_spans=[
            {
                "text": span.text,
                "reason": str(span.reason),
                "page": span.page_number,
                "bbox": list(span.bbox),
                "detail": span.detail,
            }
            for span in result.hidden_spans
        ],
        matched_patterns=result.matched_patterns
        + (["ocr_no_hidden_text_detection"] if result.used_ocr else []),
    )
    session.add(report)
    application.state = ApplicationState.EXTRACTED
    # Queued here rather than on upload: an application with no usable text has
    # nothing to evaluate, and a queue row for it would only fail three times.
    if result.visible_text.strip():
        enqueue(session, application)
    return report
