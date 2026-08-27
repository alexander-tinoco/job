from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep
from app.schemas.openings import PublicOpeningOut
from app.services import openings as service

router = APIRouter(prefix="/openings", tags=["public"])


@router.get("/{slug}", response_model=PublicOpeningOut)
def get_public_opening(slug: str, session: SessionDep) -> PublicOpeningOut:
    """The page an applicant lands on. No auth, and no internal fields."""
    opening = service.get_opening_by_slug(session, slug)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    return PublicOpeningOut(
        slug=opening.slug,
        title=opening.title,
        description=opening.description,
        company_name=opening.company.name,
        status=opening.status,
        closes_at=opening.closes_at,
    )
