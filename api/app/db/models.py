from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import (
    ApplicationState,
    DecisionKind,
    IntegrityVerdict,
    OpeningStatus,
    QueueState,
    uuid7,
)

# Store enums as native Postgres types so the database rejects an invented state,
# not just the application layer.
APPLICATION_STATE = Enum(ApplicationState, name="application_state", native_enum=True)
INTEGRITY_VERDICT = Enum(IntegrityVerdict, name="integrity_verdict", native_enum=True)
OPENING_STATUS = Enum(OpeningStatus, name="opening_status", native_enum=True)
DECISION_KIND = Enum(DecisionKind, name="decision_kind", native_enum=True)
QUEUE_STATE = Enum(QueueState, name="queue_state", native_enum=True)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    openings: Mapped[list[JobOpening]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class JobOpening(Base, TimestampMixin):
    __tablename__ = "job_openings"

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Free text written by HR when creating the opening. This is the evaluation
    # context that goes in the prompt; there is no retrieval step (plan §4).
    company_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[OpeningStatus] = mapped_column(
        OPENING_STATUS, nullable=False, default=OpeningStatus.OPEN
    )
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship(back_populates="openings")
    criteria: Mapped[list[Criterion]] = relationship(
        back_populates="opening", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="opening", cascade="all, delete-orphan"
    )


class Criterion(Base, TimestampMixin):
    __tablename__ = "criteria"
    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 100", name="weight_range"),
        UniqueConstraint("job_opening_id", "position", name="uq_criteria_opening_position"),
    )

    id: Mapped[uuid.UUID] = _pk()
    job_opening_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_openings.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    mandatory: Mapped[bool] = mapped_column(nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    opening: Mapped[JobOpening] = relationship(back_populates="criteria")


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = _pk()
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    linkedin_url: Mapped[str | None] = mapped_column(String(300))
    # Explicit, timestamped consent. Required before any processing (plan §8).
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    applications: Mapped[list[Application]] = relationship(back_populates="candidate")


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint(
            "job_opening_id", "candidate_id", name="uq_applications_opening_candidate"
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    job_opening_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_openings.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[ApplicationState] = mapped_column(
        APPLICATION_STATE, nullable=False, default=ApplicationState.RECEIVED, index=True
    )

    opening: Mapped[JobOpening] = relationship(back_populates="applications")
    candidate: Mapped[Candidate] = relationship(back_populates="applications")
    resume: Mapped[ResumeDocument | None] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )
    integrity: Mapped[IntegrityReport | None] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )
    evaluation: Mapped[Evaluation | None] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )
    decision: Mapped[HumanDecision | None] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )


class ResumeDocument(Base, TimestampMixin):
    __tablename__ = "resume_documents"
    __table_args__ = (Index("ix_resume_documents_search", "search_vector", postgresql_using="gin"),)

    id: Mapped[uuid.UUID] = _pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Two texts on purpose: the delta between them is the evidence of tampering
    # and only visible_text is ever sent to the model (plan §6, layer 1).
    visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    total_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 'simple' rather than 'spanish': résumés mix languages and we do not want
    # stemming to silently drop technology names. Revisit when tuning panel search.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(visible_text, ''))", persisted=True),
    )

    application: Mapped[Application] = relationship(back_populates="resume")


class IntegrityReport(Base, TimestampMixin):
    __tablename__ = "integrity_reports"

    id: Mapped[uuid.UUID] = _pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    verdict: Mapped[IntegrityVerdict] = mapped_column(
        INTEGRITY_VERDICT, nullable=False, default=IntegrityVerdict.CLEAN
    )
    hidden_spans: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    matched_patterns: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    application: Mapped[Application] = relationship(back_populates="integrity")


class Evaluation(Base, TimestampMixin):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = _pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Computed in Python from the rubric weights. The model never emits this
    # number, which is what keeps an injected résumé from ranking itself (plan §6).
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    relevant_years_experience: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    mandatory_requirements_met: Mapped[bool] = mapped_column(nullable=False)
    missing_requirements: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # What the model saw as risk in the candidate.
    risks: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # What our own verification objected to: an unfound quote, a criterion the
    # model invented. These are system flags, not statements about the person,
    # and the panel must not present them as the same thing.
    review_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    detected_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    needs_human_review: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Reproducibility: without these three, a two-month-old evaluation cannot be
    # explained or re-run (plan §5).
    model_id: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False)

    application: Mapped[Application] = relationship(back_populates="evaluation")
    scores: Mapped[list[CriterionScore]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class CriterionScore(Base, TimestampMixin):
    __tablename__ = "criterion_scores"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 5", name="score_range"),
        UniqueConstraint(
            "evaluation_id", "criterion_id", name="uq_criterion_scores_eval_criterion"
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("criteria.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Literal quotes. Every one is verified against visible_text before display
    # (plan §6, layer 4), together with its character offset for highlighting.
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)

    evaluation: Mapped[Evaluation] = relationship(back_populates="scores")


class HumanDecision(Base, TimestampMixin):
    __tablename__ = "human_decisions"

    id: Mapped[uuid.UUID] = _pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    kind: Mapped[DecisionKind] = mapped_column(DECISION_KIND, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_by: Mapped[str] = mapped_column(String(200), nullable=False)

    application: Mapped[Application] = relationship(back_populates="decision")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _pk()
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class JobQueue(Base, TimestampMixin):
    __tablename__ = "job_queue"
    __table_args__ = (Index("ix_job_queue_state_created", "state", "created_at"),)

    id: Mapped[uuid.UUID] = _pk()
    task: Mapped[str] = mapped_column(String(80), nullable=False)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[QueueState] = mapped_column(
        QUEUE_STATE, nullable=False, default=QueueState.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    batch_id: Mapped[str | None] = mapped_column(String(120), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)


class RuntimeState(Base, TimestampMixin):
    """Small integers the workers need to remember across restarts.

    Currently one key: the enqueued-token budget the Batch API last accepted.
    Process-global state would be relearned by every worker and lost on restart.
    """

    __tablename__ = "runtime_state"

    id: Mapped[uuid.UUID] = _pk()
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
