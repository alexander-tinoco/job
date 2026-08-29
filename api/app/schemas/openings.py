import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.types import OpeningStatus

MIN_CRITERIA = 2
MAX_CRITERIA = 8
DOMINANT_WEIGHT = 60


class CriterionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    weight: int = Field(ge=0, le=100)
    mandatory: bool = False


# More than a handful and it stops being a form anyone finishes.
MAX_SCREENING_QUESTIONS = 5


class ScreeningQuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    # The answer the opening is looking for. Never sent to the applicant.
    expected_answer: bool = True


class PublicScreeningQuestion(BaseModel):
    """What the applicant is shown.

    Carries no `expected_answer` on purpose: telling a candidate which answer
    the opening wants turns the question into a form to be filled in correctly
    rather than a fact to be stated.
    """

    id: uuid.UUID
    text: str


class OpeningCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    company_context: str = ""
    slug: str | None = None
    closes_at: datetime | None = None
    criteria: list[CriterionIn]
    screening_questions: list[ScreeningQuestionIn] = []

    @model_validator(mode="after")
    def check_screening_questions(self) -> Self:
        count = len(self.screening_questions)
        if count > MAX_SCREENING_QUESTIONS:
            raise ValueError(
                f"An opening asks at most {MAX_SCREENING_QUESTIONS} screening questions; "
                f"beyond that applicants stop finishing the form. Got {count}."
            )
        texts = [q.text.strip().lower() for q in self.screening_questions]
        repeated = sorted({t for t in texts if texts.count(t) > 1})
        if repeated:
            raise ValueError(f"Screening questions must be unique; repeated: {repeated[0]}.")
        return self

    @model_validator(mode="after")
    def check_rubric(self) -> Self:
        """The rubric decides whether the whole product produces sensible output.

        These rules are the cheap half of that problem (plan §4.2); the templates
        and worked examples are the other half.
        """
        count = len(self.criteria)
        if count < MIN_CRITERIA:
            raise ValueError(
                f"A rubric needs at least {MIN_CRITERIA} criteria; a single one cannot "
                f"discriminate between candidates. Got {count}."
            )
        if count > MAX_CRITERIA:
            raise ValueError(
                f"A rubric takes at most {MAX_CRITERIA} criteria; beyond that nobody "
                f"weights them meaningfully. Got {count}."
            )

        total = sum(c.weight for c in self.criteria)
        if total != 100:
            drift = total - 100
            direction = "over" if drift > 0 else "under"
            raise ValueError(
                f"Criterion weights must sum to 100; they sum to {total} "
                f"({abs(drift)} {direction})."
            )

        names = [c.name.strip().lower() for c in self.criteria]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"Criterion names must be unique; repeated: {', '.join(duplicates)}.")

        if not any(c.mandatory for c in self.criteria):
            raise ValueError(
                "At least one criterion must be mandatory, otherwise no candidate can "
                "ever fail the hard requirements."
            )
        return self

    @property
    def warnings(self) -> list[str]:
        """Non-blocking advice. A lopsided rubric is legal but usually a mistake."""
        return [
            f"'{c.name}' carries {c.weight}% of the score. A criterion above "
            f"{DOMINANT_WEIGHT}% makes the other criteria decorative."
            for c in self.criteria
            if c.weight > DOMINANT_WEIGHT
        ]


class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    weight: int
    mandatory: bool
    position: int


class OpeningOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    slug: str
    title: str
    description: str
    company_context: str
    status: OpeningStatus
    rubric_version: int
    closes_at: datetime | None
    criteria: list[CriterionOut]


class OpeningCreated(BaseModel):
    opening: OpeningOut
    warnings: list[str] = []


class PublicOpeningOut(BaseModel):
    """What an applicant sees.

    Deliberately omits company_context and the rubric: publishing the scoring
    criteria would tell candidates exactly what to write.
    """

    slug: str
    title: str
    description: str
    company_name: str
    status: OpeningStatus
    closes_at: datetime | None
    screening_questions: list[PublicScreeningQuestion] = []


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
