"""The work queue, in Postgres.

`SELECT ... FOR UPDATE SKIP LOCKED` is what lets two workers share a queue
without inventing a locking protocol. It is also the whole reason this project
needs neither Redis nor Celery, which is what keeps the deployment at about
$10/month (plan §2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, JobQueue
from app.db.types import ApplicationState, QueueState

TASK_EVALUATE = "evaluate"

# After this many failures the row stops being retried and waits for a human.
# Retrying forever on a poisoned row is how a queue quietly burns a budget.
MAX_ATTEMPTS = 3


def enqueue(session: Session, application: Application) -> JobQueue | None:
    """Queue an application for evaluation, unless it is already queued."""
    existing = session.scalar(
        select(JobQueue).where(
            JobQueue.application_id == application.id,
            JobQueue.task == TASK_EVALUATE,
            JobQueue.state.in_([QueueState.PENDING, QueueState.SENT]),
        )
    )
    if existing is not None:
        return None

    entry = JobQueue(task=TASK_EVALUATE, application_id=application.id)
    session.add(entry)
    session.flush()
    return entry


def claim_pending(session: Session, limit: int) -> list[JobQueue]:
    """Take up to `limit` pending rows, locking them against other workers.

    SKIP LOCKED rather than NOWAIT: a second worker should quietly take
    different rows, not fail.
    """
    rows = list(
        session.scalars(
            select(JobQueue)
            .where(JobQueue.task == TASK_EVALUATE, JobQueue.state == QueueState.PENDING)
            .order_by(JobQueue.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    return rows


def count_pending(session: Session) -> int:
    return len(
        list(
            session.scalars(
                select(JobQueue.id).where(
                    JobQueue.task == TASK_EVALUATE, JobQueue.state == QueueState.PENDING
                )
            )
        )
    )


def mark_sent(session: Session, rows: list[JobQueue], batch_id: str) -> None:
    for row in rows:
        row.state = QueueState.SENT
        row.batch_id = batch_id
        row.attempts += 1
        if row.application_id is not None:
            application = session.get(Application, row.application_id)
            if application is not None:
                application.state = ApplicationState.QUEUED
    session.flush()


def mark_done(session: Session, row: JobQueue) -> None:
    row.state = QueueState.DONE
    row.last_error = None
    session.flush()


def mark_failed(session: Session, row: JobQueue, error: str) -> None:
    """Send a row back to the queue, or give up on it and flag the application.

    A candidate whose evaluation cannot be produced must still be visible to HR
    rather than disappearing, so the application goes to `error`, not silence.
    """
    row.last_error = error[:2000]
    if row.attempts >= MAX_ATTEMPTS:
        row.state = QueueState.FAILED
        if row.application_id is not None:
            application = session.get(Application, row.application_id)
            if application is not None:
                application.state = ApplicationState.ERROR
    else:
        row.state = QueueState.PENDING
        row.batch_id = None
    session.flush()


def sent_batches(session: Session) -> list[str]:
    """Distinct batch ids still in flight.

    Several can be open at once: batches take from minutes to hours, and the
    scheduler sends every six hours regardless (plan §4.1).
    """
    rows = session.scalars(
        select(JobQueue.batch_id).where(
            JobQueue.state == QueueState.SENT, JobQueue.batch_id.is_not(None)
        )
    )
    return sorted({row for row in rows if row})


def rows_for_batch(session: Session, batch_id: str) -> dict[uuid.UUID, JobQueue]:
    """The queue rows of one batch, keyed by id so results can be matched."""
    rows = session.scalars(select(JobQueue).where(JobQueue.batch_id == batch_id))
    return {row.id: row for row in rows}


def stale_sent(session: Session, older_than: datetime) -> list[JobQueue]:
    """Rows sent before `older_than` and still unanswered.

    The completion window is 24 h and not configurable, so anything older than
    that is not slow, it is lost.
    """
    return list(
        session.scalars(
            select(JobQueue).where(
                JobQueue.state == QueueState.SENT, JobQueue.updated_at < older_than
            )
        )
    )


def now() -> datetime:
    return datetime.now(UTC)
