import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import AdminDep, SessionDep
from app.core.config import get_settings
from app.db.models import Application, JobOpening
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


def _opening(session: SessionDep, opening_id: uuid.UUID) -> JobOpening:
    opening = session.get(JobOpening, opening_id)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    return opening


@router.get("/openings/{opening_id}/applications", response_model=RankedPage)
def ranked_applications(
    opening_id: uuid.UUID,
    session: SessionDep,
    _: AdminDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RankedPage:
    return panel.ranked(session, _opening(session, opening_id), limit, offset)


@router.get("/openings/{opening_id}/search", response_model=SearchResults)
def search_applications(
    opening_id: uuid.UUID,
    session: SessionDep,
    _: AdminDep,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
) -> SearchResults:
    return panel.search(session, _opening(session, opening_id), q, limit)


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def application_detail(
    application_id: uuid.UUID, session: SessionDep, _: AdminDep
) -> ApplicationDetail:
    found = panel.detail(session, application_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return found


@router.get("/applications/{application_id}/resume")
def download_resume(application_id: uuid.UUID, session: SessionDep, _: AdminDep) -> FileResponse:
    """Serve the original PDF as a download, never inline.

    This file was uploaded by a stranger and PDF viewers execute JavaScript.
    Rendering it inline on the panel's own origin would be a cross-site
    scripting hole with an HR session attached, so it is forced to download and
    sandboxed on the way out.
    """
    application = session.get(Application, application_id)
    if application is None or application.resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Résumé not found.")

    path = Path(get_settings().uploads_dir) / application.resume.storage_path
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, detail="The stored file is no longer available.")

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


@router.post(
    "/applications/{application_id}/decision",
    response_model=DecisionOut,
    status_code=status.HTTP_201_CREATED,
)
def record_decision(
    application_id: uuid.UUID, payload: DecisionIn, session: SessionDep, _: AdminDep
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
