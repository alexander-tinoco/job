import uuid
from decimal import Decimal

from pydantic import BaseModel


class SideEvidence(BaseModel):
    application_id: uuid.UUID
    score: int
    # What this criterion added to that candidate's overall score.
    contribution: Decimal
    justification: str
    quotes: list[str]


class ComparedCriterion(BaseModel):
    criterion_id: uuid.UUID
    criterion_name: str
    weight: int
    mandatory: bool
    sides: list[SideEvidence]
    # Whoever is ahead on this row. Empty when everybody scored the same.
    leaders: list[uuid.UUID]
    # Points of the overall score separating best from worst on this row.
    spread: Decimal


class ComparedCandidate(BaseModel):
    id: uuid.UUID
    name: str
    overall_score: Decimal
    summary: str
    relevant_years_experience: Decimal
    mandatory_requirements_met: bool
    tampered: bool
    decision: str | None


class ComparisonOut(BaseModel):
    opening_title: str
    candidates: list[ComparedCandidate]
    criteria: list[ComparedCriterion]
    # The one or two criteria carrying the difference.
    decisive: list[str]
