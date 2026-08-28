import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, Response

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.db.models import Application, JobOpening
from app.ingest import render
from app.schemas.panel import (
    ApplicationDetail,
    DecisionIn,
    DecisionOut,
    RankedPage,
    SearchResults,
)
from app.services import decisions, panel

router = APIRouter(prefix="/api/v1", tags=["panel"])

MAX_PAGE = 200


def _stored_resume(session: SessionDep, application_id: uuid.UUID) -> Path:
    application = session.get(Application, application_id)
    if application is None or application.resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Résumé not found.")
    path = Path(get_settings().uploads_dir) / application.resume.storage_path
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, detail="The stored file is no longer available.")
    return path


def _opening(session: SessionDep, opening_id: uuid.UUID) -> JobOpening:
    opening = session.get(JobOpening, opening_id)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    return opening


@router.get("/openings/{opening_id}/applications", response_model=RankedPage)
def ranked_applications(
    opening_id: uuid.UUID,
    session: SessionDep,
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RankedPage:
    return panel.ranked(session, _opening(session, opening_id), limit, offset)


@router.get("/openings/{opening_id}/search", response_model=SearchResults)
def search_applications(
    opening_id: uuid.UUID,
    session: SessionDep,
    _: CurrentUser,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
) -> SearchResults:
    return panel.search(session, _opening(session, opening_id), q, limit)


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def application_detail(
    application_id: uuid.UUID, session: SessionDep, _: CurrentUser
) -> ApplicationDetail:
    found = panel.detail(session, application_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return found


@router.get("/applications/{application_id}/resume")
def download_resume(application_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> FileResponse:
    """Serve the original PDF as a download, never inline.

    This file was uploaded by a stranger and PDF viewers execute JavaScript.
    Rendering it inline on the panel's own origin would be a cross-site
    scripting hole with an HR session attached, so it is forced to download and
    sandboxed on the way out.
    """
    path = _stored_resume(session, application_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"resume-{application_id}.pdf",
        headers={
            "Content-Disposition": f'attachment; filename="resume-{application_id}.pdf"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "no-store",
        },
    )


@router.get("/applications/{application_id}/resume/pages/{number}")
def resume_page(
    application_id: uuid.UUID, number: int, session: SessionDep, _: CurrentUser
) -> Response:
    """One page of the résumé, rendered server-side as a PNG.

    An image, not the PDF. Showing the document inline is what the panel needs;
    showing it *as a PDF* would put a stranger's file, and whatever script it
    carries, on the panel's own origin.
    """
    path = _stored_resume(session, application_id)
    try:
        image = render.render_page(path, number)
    except render.PageOutOfRangeError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return Response(
        image,
        media_type="image/png",
        headers={
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "X-Content-Type-Options": "nosniff",
            # The rendering is deterministic and the file never changes, but it
            # is personal data: cached in the browser, never by a proxy.
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post(
    "/applications/{application_id}/decision",
    response_model=DecisionOut,
    status_code=status.HTTP_201_CREATED,
)
def record_decision(
    application_id: uuid.UUID, payload: DecisionIn, session: SessionDep, _: CurrentUser
) -> DecisionOut:
    """The human decision. It never overwrites the model's; both are kept."""
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found.")
    try:
        decision = decisions.decide(session, application, payload)
    except decisions.AlreadyDecidedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    return DecisionOut.model_validate(decision)
