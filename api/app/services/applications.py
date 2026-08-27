from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, Candidate, JobOpening
from app.db.types import OpeningStatus
from app.schemas.applications import ApplicantDetails


class OpeningClosedError(Exception):
    """Applications are no longer accepted for this opening."""


class AlreadyAppliedError(Exception):
    """This candidate already applied to this opening."""


def get_or_create_candidate(session: Session, details: ApplicantDetails) -> Candidate:
    """One person, many applications.

    Deduplicated by email so the panel can show a candidate's history across
    openings instead of treating each application as a stranger.
    """
    candidate = session.scalar(select(Candidate).where(Candidate.email == details.email))
    if candidate is not None:
        candidate.full_name = details.full_name
        candidate.phone = details.phone or candidate.phone
        candidate.linkedin_url = details.linkedin_url or candidate.linkedin_url
        return candidate

    candidate = Candidate(
        full_name=details.full_name,
        email=details.email,
        phone=details.phone,
        linkedin_url=details.linkedin_url,
        # Recorded server-side. A client-supplied timestamp would be worthless
        # as evidence of consent (plan §8).
        consented_at=datetime.now(UTC),
    )
    session.add(candidate)
    session.flush()
    return candidate


def create_application(session: Session, opening: JobOpening, candidate: Candidate) -> Application:
    if opening.status is not OpeningStatus.OPEN:
        raise OpeningClosedError("This opening is no longer accepting applications.")

    existing = session.scalar(
        select(Application).where(
            Application.job_opening_id == opening.id,
            Application.candidate_id == candidate.id,
        )
    )
    if existing is not None:
        raise AlreadyAppliedError("You have already applied to this opening.")

    application = Application(opening=opening, candidate=candidate)
    session.add(application)
    session.flush()
    return application
