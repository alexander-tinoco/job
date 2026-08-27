import uuid

from fastapi import APIRouter, HTTPException, status

from app.ai.client import MissingApiKeyError
from app.api.deps import AdminDep, SessionDep
from app.db.models import Application
from app.schemas.evaluations import EvaluationOut
from app.services.evaluation import NotReadyError, evaluate_application

router = APIRouter(prefix="/api/v1", tags=["evaluations"])


@router.post(
    "/applications/{application_id}/evaluate",
    response_model=EvaluationOut,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_now(application_id: uuid.UUID, session: SessionDep, _: AdminDep) -> EvaluationOut:
    """Evaluate one candidate synchronously, at full price.

    The batch path is what an opening runs on (plan §4.1). This exists for the
    case where HR wants to look at one specific person without waiting, which
    matters more than it sounds: a three-request batch took over twelve minutes
    in measurement.
    """
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found.")
    if application.evaluation is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This application has already been evaluated."
        )

    try:
        evaluation = evaluate_application(session, application)
    except NotReadyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissingApiKeyError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    session.commit()
    return EvaluationOut.model_validate(evaluation)
