"""Minimal builders so tests read as intent, not as setup noise."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    Candidate,
    Company,
    Criterion,
    Evaluation,
    JobOpening,
)


def make_opening(session: Session, slug: str = "backend-engineer") -> JobOpening:
    company = Company(name="Acme")
    opening = JobOpening(
        company=company,
        slug=slug,
        title="Backend Engineer",
        description="We need someone to own our API.",
        company_context="Small team, Python shop, ships weekly.",
    )
    opening.criteria = [
        Criterion(
            name="Python", description="Depth in Python", weight=60, mandatory=True, position=1
        ),
        Criterion(name="Postgres", description="Relational modelling", weight=40, position=2),
    ]
    session.add(opening)
    session.flush()
    return opening


def make_application(session: Session, opening: JobOpening, email: str) -> Application:
    candidate = Candidate(
        full_name="Ada Lovelace",
        email=email,
        consented_at=datetime.now(UTC),
    )
    application = Application(opening=opening, candidate=candidate)
    session.add(application)
    session.flush()
    return application


def make_evaluation(application: Application) -> Evaluation:
    return Evaluation(
        application=application,
        overall_score=Decimal("82.50"),
        relevant_years_experience=Decimal("6.0"),
        mandatory_requirements_met=True,
        summary="Strong Python background.",
        model_id="gpt-5.4-mini",
        prompt_version="v1",
        rubric_version=1,
    )
