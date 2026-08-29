from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.api.deps import ClientIp, SessionDep
from app.db.models import ResumeDocument
from app.schemas.applications import ApplicantDetails, ApplicationReceipt
from app.services import applications as service
from app.services import ingestion, limits, screening, storage
from app.services import openings as openings_service

router = APIRouter(prefix="/openings", tags=["public"])


@router.post(
    "/{slug}/apply",
    response_model=ApplicationReceipt,
    status_code=status.HTTP_201_CREATED,
)
async def apply(
    slug: str,
    session: SessionDep,
    source_ip: ClientIp,
    full_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    consent: Annotated[bool, Form()],
    resume: Annotated[UploadFile, File()],
    phone: Annotated[str | None, Form()] = None,
    linkedin_url: Annotated[str | None, Form()] = None,
    # JSON in a form field: the questions are per-opening, so the browser cannot
    # name the fields in advance.
    answers: Annotated[str | None, Form()] = None,
) -> ApplicationReceipt:
    """Public application endpoint. No auth: the slug is the invitation."""
    opening = openings_service.get_opening_by_slug(session, slug)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")

    # Before anything is written or extracted. The upload has already crossed
    # the wire by now, but the disk write, PyMuPDF and the model call have not.
    try:
        limits.check_application(session, email, source_ip)
    except limits.RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    try:
        stated = screening.parse(answers)
    except screening.AnswerError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    if not consent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Consent to process your data is required to apply.",
        )

    try:
        details = ApplicantDetails(
            full_name=full_name, email=email, phone=phone, linkedin_url=linkedin_url
        )
    except ValidationError as exc:
        # Built by hand from form fields, so FastAPI never sees it as request
        # validation; without this the applicant gets a 500 for a typo.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(include_url=False, include_context=False, include_input=False),
        ) from exc

    candidate = service.get_or_create_candidate(session, details)
    try:
        application = service.create_application(session, opening, candidate)
    except service.OpeningClosedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.AlreadyAppliedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        stored = await storage.save_resume(resume, str(application.id))
    except storage.UploadTooLargeError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except storage.NotAPdfError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    try:
        screening.record(application, opening, stated)
    except screening.AnswerError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    application.resume = ResumeDocument(storage_path=stored.relative_path)
    session.flush()

    # Deterministic, free and fast, so it runs inline: the panel shows the
    # résumé, its text and any tampering flags from the moment it arrives,
    # instead of waiting for the evaluation batch (plan §4.1).
    ingestion.ingest_application(session, application)
    limits.record_application(session, email, source_ip)
    session.commit()

    return ApplicationReceipt(
        application_id=application.id,
        state=application.state,
        opening_title=opening.title,
        message="Application received. You will hear from us after the opening closes.",
    )
