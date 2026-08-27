import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CriterionScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    criterion_id: uuid.UUID
    score: int
    justification: str
    # Each quote carries `found` and its offsets into the résumé, so the panel
    # can highlight it and show at a glance which claims are backed.
    evidence: list[dict[str, object]]


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    overall_score: Decimal
    relevant_years_experience: Decimal
    mandatory_requirements_met: bool
    missing_requirements: list[str]
    risks: list[str]
    detected_skills: list[str]
    summary: str
    needs_human_review: bool
    model_id: str
    prompt_version: str
    rubric_version: int
    scores: list[CriterionScoreOut]
