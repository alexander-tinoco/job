import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import ApplicationState, DecisionKind, IntegrityVerdict


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: DecisionKind
    reason: str
    decided_by: str
    created_at: datetime


class ApplicationSummary(BaseModel):
    """One row of the ranking."""

    id: uuid.UUID
    candidate_name: str
    candidate_email: str
    state: ApplicationState
    applied_at: datetime
    # Absent until the batch comes back. The row still appears, because the
    # résumé and its flags are useful before the score exists (plan §4.1).
    overall_score: Decimal | None
    summary: str
    mandatory_requirements_met: bool | None
    integrity: IntegrityVerdict | None
    hidden_text_chars: int
    # Objections from our own verification, not observations about the person.
    needs_human_review: bool
    decision: DecisionOut | None


class EvidenceOut(BaseModel):
    quote: str
    found: bool
    # Offsets into `resume_text`, so the panel highlights the exact span.
    start: int | None
    end: int | None


class CriterionScoreOut(BaseModel):
    criterion_id: uuid.UUID
    criterion_name: str
    weight: int
    mandatory: bool
    score: int
    justification: str
    evidence: list[EvidenceOut]


class HiddenSpanOut(BaseModel):
    text: str
    reason: str
    page: int
    detail: str


class IntegrityOut(BaseModel):
    verdict: IntegrityVerdict
    hidden_spans: list[HiddenSpanOut]
    matched_patterns: list[str]


class ApplicationDetail(BaseModel):
    id: uuid.UUID
    opening_id: uuid.UUID
    opening_title: str
    candidate_name: str
    candidate_email: str
    candidate_phone: str | None
    candidate_linkedin: str | None
    state: ApplicationState
    applied_at: datetime
    consented_at: datetime

    # The sanitized text, which is also what the model was given. Evidence
    # offsets point into this string and nowhere else.
    resume_text: str
    page_count: int

    overall_score: Decimal | None
    relevant_years_experience: Decimal | None
    mandatory_requirements_met: bool | None
    missing_requirements: list[str]
    detected_skills: list[str]
    summary: str
    # What the model saw as risk in the candidate.
    risks: list[str]
    # What our verification objected to. Shown separately: a candidate with an
    # unfound quote does not have a problem, our evaluation does.
    review_flags: list[str]
    needs_human_review: bool
    model_id: str | None
    prompt_version: str | None
    rubric_version: int | None

    criteria: list[CriterionScoreOut]
    integrity: IntegrityOut | None
    decision: DecisionOut | None


class RankedPage(BaseModel):
    opening_id: uuid.UUID
    opening_title: str
    total: int
    evaluated: int
    items: list[ApplicationSummary]


class DecisionIn(BaseModel):
    kind: DecisionKind
    reason: str = Field(min_length=1, max_length=2000)
    decided_by: str = Field(min_length=1, max_length=200)


class SearchHit(BaseModel):
    application_id: uuid.UUID
    candidate_name: str
    overall_score: Decimal | None
    excerpt: str


class SearchResults(BaseModel):
    query: str
    hits: list[SearchHit]
