import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.db.models import Application
from app.schemas.duplicates import DuplicateMatch, DuplicatesOut
from app.services import duplicates

router = APIRouter(prefix="/api/v1", tags=["duplicates"])


@router.get("/applications/{application_id}/duplicates", response_model=DuplicatesOut)
def resume_duplicates(
    application_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> DuplicatesOut:
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return DuplicatesOut(
        matches=[DuplicateMatch(**vars(match)) for match in duplicates.find(session, application)]
    )
