import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.db.models import JobOpening
from app.schemas.compare import ComparisonOut
from app.services import compare as compare_service

router = APIRouter(prefix="/api/v1", tags=["compare"])


@router.get("/openings/{opening_id}/compare", response_model=ComparisonOut)
def compare_candidates(
    opening_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    ids: Annotated[list[uuid.UUID], Query(min_length=2)],
) -> ComparisonOut:
    opening = session.get(JobOpening, opening_id)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    try:
        return compare_service.compare(session, opening, ids)
    except compare_service.TooManyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except compare_service.NotComparableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
