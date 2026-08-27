"""The strict output schema of the single AI call.

Two absences are deliberate:

* **No overall score.** The model rates criteria 0-5; Python applies the rubric
  weights to produce the number that orders the ranking (plan §6, layer 3). A
  résumé that talks its way into a high criterion score still cannot rank itself.
* **No protected attributes.** Age, gender, nationality, origin, photo and
  marital status are not modelled, so they cannot be returned even if a résumé
  volunteers them (plan §8).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

MIN_SCORE = 0
MAX_SCORE = 5


class CriterionAssessment(BaseModel):
    """One rubric criterion, scored with quoted evidence."""

    criterion_name: str = Field(description="Exactly as given in the rubric.")
    score: int = Field(ge=MIN_SCORE, le=MAX_SCORE)
    justification: str = Field(description="At most 40 words.")
    evidence: list[str] = Field(
        description=(
            "Literal quotes copied character for character from the résumé. "
            "Every quote is verified against the source text; invented quotes "
            "flag the evaluation for human review."
        )
    )


class EvaluationOutput(BaseModel):
    criteria: list[CriterionAssessment]
    relevant_years_experience: float
    mandatory_requirements_met: bool
    missing_requirements: list[str]
    risks: list[str]
    detected_skills: list[str]
    summary: str = Field(description="At most 60 words.")
