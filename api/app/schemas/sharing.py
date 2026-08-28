import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import ShareScope
from app.schemas.panel import CriterionScoreOut


class ShareCreate(BaseModel):
    scope: ShareScope = ShareScope.SHORTLIST
    label: str = Field(default="", max_length=200)
    days: int = Field(default=14, ge=1, le=90)


class ShareLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope: ShareScope
    label: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    view_count: int
    last_viewed_at: datetime | None


class ShareCreated(BaseModel):
    link: ShareLinkOut
    # The only time the token is ever returned. It is stored hashed, so it
    # cannot be shown again — copy it now or make a new link.
    url_path: str


class SharedCandidate(BaseModel):
    """What someone without an account may see about one candidate."""

    id: uuid.UUID
    name: str
    overall_score: Decimal
    summary: str
    relevant_years_experience: Decimal
    mandatory_requirements_met: bool
    detected_skills: list[str]
    criteria: list[CriterionScoreOut]
    resume_text: str
    page_count: int
    tampered: bool
    shortlisted: bool
    # Deliberately absent: email, phone, LinkedIn, the reviewer's reason, the
    # audit trail, and everyone who was declined.


class SharedView(BaseModel):
    opening_title: str
    company_name: str
    scope: ShareScope
    expires_at: datetime
    candidates: list[SharedCandidate]
