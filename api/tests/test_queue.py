"""The Postgres work queue."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, JobQueue
from app.db.types import ApplicationState, QueueState
from app.services import queue
from tests.factories import make_application, make_opening


def _queued(session: Session, email: str) -> tuple[Application, JobQueue]:
    opening = make_opening(session, slug=f"q-{email.split('@')[0]}")
    application = make_application(session, opening, email)
    entry = queue.enqueue(session, application)
    assert entry is not None
    return application, entry


def test_enqueue_creates_a_pending_row(session: Session) -> None:
    _, entry = _queued(session, "a@example.com")

    assert entry.state is QueueState.PENDING
    assert entry.task == queue.TASK_EVALUATE
    assert entry.attempts == 0


def test_enqueueing_twice_does_not_duplicate_work(session: Session) -> None:
    application, _ = _queued(session, "b@example.com")

    assert queue.enqueue(session, application) is None
    assert queue.count_pending(session) == 1


def test_claiming_returns_oldest_first(session: Session) -> None:
    first, _ = _queued(session, "c@example.com")
    second, _ = _queued(session, "d@example.com")
    session.flush()

    claimed = queue.claim_pending(session, limit=10)

    assert [row.application_id for row in claimed] == [first.id, second.id]


def test_marking_sent_moves_the_application_to_queued(session: Session) -> None:
    application, entry = _queued(session, "e@example.com")

    queue.mark_sent(session, [entry], "batch_123")

    assert entry.state is QueueState.SENT
    assert entry.batch_id == "batch_123"
    assert entry.attempts == 1
    assert application.state is ApplicationState.QUEUED


def test_a_failure_goes_back_to_pending_for_another_try(session: Session) -> None:
    application, entry = _queued(session, "f@example.com")
    queue.mark_sent(session, [entry], "batch_123")

    queue.mark_failed(session, entry, "transient error")

    assert entry.state is QueueState.PENDING
    assert entry.batch_id is None
    assert entry.last_error == "transient error"
    assert application.state is not ApplicationState.ERROR


def test_a_poisoned_row_stops_retrying_and_surfaces_the_candidate(session: Session) -> None:
    """Retrying forever is how a queue quietly burns a budget."""
    application, entry = _queued(session, "g@example.com")

    for _ in range(queue.MAX_ATTEMPTS):
        queue.mark_sent(session, [entry], "batch_x")
        queue.mark_failed(session, entry, "always fails")

    assert entry.state is QueueState.FAILED
    # The candidate must still be visible to HR, not silently dropped.
    assert application.state is ApplicationState.ERROR


def test_batches_in_flight_are_listed_once_each(session: Session) -> None:
    _, first = _queued(session, "h@example.com")
    _, second = _queued(session, "i@example.com")
    queue.mark_sent(session, [first, second], "batch_same")

    assert queue.sent_batches(session) == ["batch_same"]


def test_rows_for_a_batch_are_keyed_by_id(session: Session) -> None:
    _, entry = _queued(session, "j@example.com")
    queue.mark_sent(session, [entry], "batch_keyed")

    rows = queue.rows_for_batch(session, "batch_keyed")

    assert set(rows) == {entry.id}


def test_done_clears_the_error(session: Session) -> None:
    _, entry = _queued(session, "k@example.com")
    queue.mark_failed(session, entry, "something")

    queue.mark_done(session, entry)

    assert entry.state is QueueState.DONE
    assert entry.last_error is None


def test_only_pending_rows_are_counted(session: Session) -> None:
    _, first = _queued(session, "l@example.com")
    _queued(session, "m@example.com")
    queue.mark_sent(session, [first], "batch_z")

    assert queue.count_pending(session) == 1


def test_the_queue_row_survives_in_the_database(session: Session) -> None:
    _queued(session, "n@example.com")
    session.commit()

    assert session.scalar(select(JobQueue)) is not None
