import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.db.models import AuditLog, JobOpening
from app.schemas.lifecycle import AuditEntry, ErasureRequest, ErasureResult, SweepResult
from app.services import exports, lifecycle

router = APIRouter(prefix="/api/v1", tags=["lifecycle"])


@router.get("/openings/{opening_id}/export.csv")
def export_opening(opening_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> Response:
    opening = session.get(JobOpening, opening_id)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")

    body = exports.opening_csv(session, opening)
    name = exports.filename_for(opening.id, opening.slug)
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/audit", response_model=list[AuditEntry])
def audit_trail(
    session: SessionDep,
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEntry]:
    """Who did what. The record that says a person made each decision."""
    rows = session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return [AuditEntry.model_validate(row) for row in rows]


@router.get("/data-subject/{email}")
def subject_access(email: str, session: SessionDep, _: CurrentUser) -> dict[str, object]:
    """Everything held about one person."""
    found = lifecycle.export_for(session, email)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No record for that address.")
    return found


@router.post("/data-subject/erase", response_model=ErasureResult)
def erase_subject(payload: ErasureRequest, session: SessionDep, user: CurrentUser) -> ErasureResult:
    """Delete everything about one person, keeping the audit anonymous."""
    erased = lifecycle.erase(session, payload.email, user.email)
    if erased is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No record for that address.")
    session.commit()
    return ErasureResult(applications=erased.applications, files_deleted=erased.files_deleted)


@router.post("/retention/sweep", response_model=SweepResult)
def run_sweep(session: SessionDep, _: CurrentUser) -> SweepResult:
    """Delete what is past its retention window. Also runs on the worker's tick."""
    swept = lifecycle.sweep(session)
    session.commit()
    return SweepResult(
        applications=swept.applications,
        files_deleted=swept.files_deleted,
        files_missing=swept.files_missing,
    )
