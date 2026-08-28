import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.db.models import Company
from app.schemas.openings import (
    CompanyCreate,
    CompanyOut,
    OpeningCreate,
    OpeningCreated,
    OpeningOut,
)
from app.services import openings as service
from app.services.rubric_templates import TEMPLATES, RubricTemplate

router = APIRouter(prefix="/api/v1", tags=["openings"])


@router.get("/rubric-templates", response_model=list[RubricTemplate])
def list_rubric_templates(_: CurrentUser) -> list[RubricTemplate]:
    return TEMPLATES


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, session: SessionDep, _: CurrentUser) -> CompanyOut:
    company = service.create_company(session, payload.name)
    session.commit()
    return CompanyOut.model_validate(company)


@router.post(
    "/companies/{company_id}/openings",
    response_model=OpeningCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_opening(
    company_id: uuid.UUID, payload: OpeningCreate, session: SessionDep, _: CurrentUser
) -> OpeningCreated:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Company not found.")
    opening = service.create_opening(session, company, payload)
    session.commit()
    return OpeningCreated(opening=OpeningOut.model_validate(opening), warnings=payload.warnings)


@router.get("/openings", response_model=list[OpeningOut])
def list_openings(session: SessionDep, _: CurrentUser) -> list[OpeningOut]:
    return [OpeningOut.model_validate(o) for o in service.list_openings(session)]


@router.get("/openings/{opening_id}", response_model=OpeningOut)
def get_opening(opening_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> OpeningOut:
    opening = service.get_opening(session, opening_id)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    return OpeningOut.model_validate(opening)


@router.post("/openings/{opening_id}/close", response_model=OpeningOut)
def close_opening(opening_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> OpeningOut:
    opening = service.get_opening(session, opening_id)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    service.close_opening(session, opening)
    session.commit()
    return OpeningOut.model_validate(opening)
