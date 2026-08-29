import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.slug import slugify
from app.db.models import Company, Criterion, JobOpening, ScreeningQuestion
from app.db.types import OpeningStatus
from app.schemas.openings import OpeningCreate


def create_company(session: Session, name: str) -> Company:
    company = Company(name=name)
    session.add(company)
    session.flush()
    return company


def _unique_slug(session: Session, desired: str) -> str:
    """Append a counter until the slug is free.

    The slug is the URL an applicant receives, so a collision between two
    openings would silently send candidates to the wrong one.
    """
    base = slugify(desired)
    candidate = base
    suffix = 1
    while session.scalar(
        select(func.count()).select_from(JobOpening).where(JobOpening.slug == candidate)
    ):
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


class SecondCompanyError(Exception):
    """A deployment holds one company, and this one already has it."""


def create_company_once(session: Session, name: str) -> Company:
    """Create the deployment's company, and refuse to create a second.

    The MVP is one company per deployment (plan §7, "Out"): there is no tenant
    on `User`, so the panel shows every opening in the database to everyone who
    can sign in. That is correct for one company and a silent data leak for two.

    Enforced rather than assumed. The assumption was written down and the code
    allowed the opposite, which is the shape most tenancy leaks have.
    """
    existing = session.scalar(select(Company))
    if existing is not None:
        raise SecondCompanyError(
            f"This deployment already holds {existing.name!r}. One company per deployment: "
            "everyone who can sign in sees every opening, so a second company here would "
            "show each one the other's candidates. Run a second deployment instead."
        )
    return create_company(session, name)


def create_opening(session: Session, company: Company, payload: OpeningCreate) -> JobOpening:
    opening = JobOpening(
        company=company,
        slug=_unique_slug(session, payload.slug or payload.title),
        title=payload.title,
        description=payload.description,
        company_context=payload.company_context,
        closes_at=payload.closes_at,
        criteria=[
            Criterion(
                name=c.name,
                description=c.description,
                weight=c.weight,
                mandatory=c.mandatory,
                position=index,
            )
            for index, c in enumerate(payload.criteria, start=1)
        ],
        screening_questions=[
            ScreeningQuestion(text=q.text, expected_answer=q.expected_answer, position=index)
            for index, q in enumerate(payload.screening_questions, start=1)
        ],
    )
    session.add(opening)
    session.flush()
    return opening


def get_opening(session: Session, opening_id: uuid.UUID) -> JobOpening | None:
    return session.scalar(
        select(JobOpening)
        .where(JobOpening.id == opening_id)
        .options(selectinload(JobOpening.criteria))
    )


def get_opening_by_slug(session: Session, slug: str) -> JobOpening | None:
    return session.scalar(
        select(JobOpening)
        .where(JobOpening.slug == slug)
        .options(selectinload(JobOpening.criteria), selectinload(JobOpening.company))
    )


def list_openings(session: Session) -> list[JobOpening]:
    return list(
        session.scalars(
            select(JobOpening)
            .order_by(JobOpening.created_at.desc())
            .options(selectinload(JobOpening.criteria))
        )
    )


def close_opening(session: Session, opening: JobOpening) -> JobOpening:
    opening.status = OpeningStatus.CLOSED
    session.flush()
    return opening
