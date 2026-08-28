"""Sending, splitting and collecting. No test calls the API."""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.ai.schema import EvaluationOutput
from app.db.models import Application, Evaluation
from app.db.types import ApplicationState, QueueState
from app.services import queue
from app.workers import scheduler
from tests.factories import make_application, make_opening

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fresh_budget() -> None:
    scheduler.reset_budget()


def _ready(session: Session, email: str, slug: str) -> Application:
    """An application with extracted text, queued and ready to send."""
    opening = make_opening(session, slug=slug)
    application = make_application(session, opening, email)
    from app.db.models import ResumeDocument

    application.resume = ResumeDocument(
        storage_path=f"{application.id}/cv.pdf",
        visible_text="Ada Lovelace. Six years of Python and PostgreSQL at scale.",
    )
    application.state = ApplicationState.EXTRACTED
    session.flush()
    queue.enqueue(session, application)
    session.flush()
    return application


def _recorded_output() -> EvaluationOutput:
    fixture = json.loads((FIXTURES / "strong_candidate.json").read_text(encoding="utf-8"))
    return EvaluationOutput.model_validate(fixture["output"])


# --- When to send (plan §4.1) ---


@pytest.mark.parametrize(
    ("hour", "pending", "expected"),
    [
        (6, 3, True),  # a scheduled slot
        (7, 3, False),  # between slots, nothing urgent
        (7, 50, True),  # the pile-up trigger
        (7, 200, True),
        (6, 0, False),  # nothing to send
    ],
)
def test_send_windows_and_the_pile_up_trigger(hour: int, pending: int, expected: bool) -> None:
    assert scheduler.should_send(hour, pending) is expected


# --- Splitting to the enqueued-token budget ---


def test_a_send_is_cut_to_the_token_budget(session: Session) -> None:
    from app.ai.batch import BatchItem
    from app.services.evaluation import build_request

    applications = [_ready(session, f"s{i}@example.com", f"sched-{i}") for i in range(5)]
    pairs = [
        (queue.claim_pending(session, 10)[i], BatchItem(str(uuid.uuid4()), build_request(a)))
        for i, a in enumerate(applications)
    ]

    one = scheduler.fit_to_budget(pairs, budget=1)
    generous = scheduler.fit_to_budget(pairs, budget=10_000_000)

    # Never returns an empty send: one oversized item still goes, alone.
    assert len(one) == 1
    assert len(generous) == 5


def test_a_rejection_narrows_the_budget_for_next_time(session: Session) -> None:
    """The real ceiling is the API's, not a constant we guessed."""
    before = scheduler.token_budget()

    scheduler.remember_limit(attempted=40_000)

    assert scheduler.token_budget() == 20_000
    assert scheduler.token_budget() < before


def test_the_budget_never_collapses_to_nothing() -> None:
    for _ in range(20):
        scheduler.remember_limit(attempted=scheduler.token_budget())

    assert scheduler.token_budget() >= scheduler.MIN_TOKEN_BUDGET


def test_a_limit_error_is_recognised_and_others_are_not() -> None:
    assert scheduler._looks_like_a_limit(RuntimeError("Enqueued token limit exceeded")) is True
    assert scheduler._looks_like_a_limit(RuntimeError("token limit reached")) is True
    assert scheduler._looks_like_a_limit(RuntimeError("connection reset")) is False


# --- Sending ---


def test_sending_marks_rows_and_applications(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = _ready(session, "send@example.com", "sched-send")
    monkeypatch.setattr("app.ai.batch.submit", lambda items: "batch_sent_1")

    outcome = scheduler.send_once(session, hour=6)

    assert outcome.batch_id == "batch_sent_1"
    assert outcome.sent == 1
    assert application.state is ApplicationState.QUEUED


def test_a_rejected_send_does_not_lose_the_queue_rows(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(session, "reject@example.com", "sched-reject")

    def boom(items: object) -> str:
        raise RuntimeError("Enqueued token limit exceeded for this batch")

    monkeypatch.setattr("app.ai.batch.submit", boom)
    outcome = scheduler.send_once(session, hour=6)

    assert outcome.batch_id is None
    assert scheduler.token_budget() < scheduler.DEFAULT_TOKEN_BUDGET


def test_an_application_with_no_text_is_failed_not_sent(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    opening = make_opening(session, slug="sched-empty")
    application = make_application(session, opening, "empty@example.com")
    entry = queue.enqueue(session, application)
    assert entry is not None
    session.flush()
    monkeypatch.setattr("app.ai.batch.submit", lambda items: "batch_never")

    scheduler.send_once(session, hour=6)

    assert entry.state is QueueState.PENDING
    assert entry.last_error is not None


# --- Collecting ---


def test_results_are_matched_by_custom_id_not_by_position(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batch output arrives in arbitrary order; position would pair the wrong rows."""
    from app.ai.batch import BatchResult

    first = _ready(session, "one@example.com", "sched-one")
    second = _ready(session, "two@example.com", "sched-two")
    rows = queue.claim_pending(session, 10)
    queue.mark_sent(session, rows, "batch_order")
    by_application = {row.application_id: row for row in rows}

    # Deliberately reversed relative to the queue order.
    reversed_results = [
        BatchResult(
            custom_id=str(by_application[second.id].id), output=_recorded_output(), error=None
        ),
        BatchResult(
            custom_id=str(by_application[first.id].id), output=_recorded_output(), error=None
        ),
    ]
    monkeypatch.setattr("app.ai.batch.status", lambda batch_id: "completed")
    monkeypatch.setattr("app.ai.batch.collect", lambda batch_id: reversed_results)

    stored = scheduler.collect_once(session)

    assert stored == 2
    assert first.evaluation is not None
    assert second.evaluation is not None
    assert first.evaluation.application_id == first.id
    assert second.evaluation.application_id == second.id


def test_a_partial_failure_does_not_lose_the_rest(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ai.batch import BatchResult

    good = _ready(session, "good@example.com", "sched-good")
    bad = _ready(session, "bad@example.com", "sched-bad")
    rows = queue.claim_pending(session, 10)
    queue.mark_sent(session, rows, "batch_partial")
    by_application = {row.application_id: row for row in rows}

    monkeypatch.setattr("app.ai.batch.status", lambda batch_id: "completed")
    monkeypatch.setattr(
        "app.ai.batch.collect",
        lambda batch_id: [
            BatchResult(
                custom_id=str(by_application[good.id].id), output=_recorded_output(), error=None
            ),
            BatchResult(
                custom_id=str(by_application[bad.id].id), output=None, error="model refused"
            ),
        ],
    )

    stored = scheduler.collect_once(session)

    assert stored == 1
    assert good.evaluation is not None
    assert bad.evaluation is None
    assert by_application[bad.id].last_error == "model refused"


def test_a_row_missing_from_the_output_is_failed_not_left_hanging(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(session, "missing@example.com", "sched-missing")
    rows = queue.claim_pending(session, 10)
    queue.mark_sent(session, rows, "batch_missing")

    monkeypatch.setattr("app.ai.batch.status", lambda batch_id: "completed")
    monkeypatch.setattr("app.ai.batch.collect", lambda batch_id: [])

    scheduler.collect_once(session)

    assert rows[0].state is QueueState.PENDING
    assert rows[0].last_error == "missing from batch output"


def test_an_unfinished_batch_is_left_alone(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(session, "waiting@example.com", "sched-waiting")
    rows = queue.claim_pending(session, 10)
    queue.mark_sent(session, rows, "batch_waiting")
    monkeypatch.setattr("app.ai.batch.status", lambda batch_id: "in_progress")

    assert scheduler.collect_once(session) == 0
    assert rows[0].state is QueueState.SENT


def test_a_failed_batch_fails_all_of_its_rows(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(session, "dead@example.com", "sched-dead")
    rows = queue.claim_pending(session, 10)
    queue.mark_sent(session, rows, "batch_dead")
    monkeypatch.setattr("app.ai.batch.status", lambda batch_id: "expired")

    scheduler.collect_once(session)

    assert rows[0].last_error == "batch expired"


def test_the_stored_evaluation_records_its_provenance(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ai.batch import BatchResult

    application = _ready(session, "prov@example.com", "sched-prov")
    rows = queue.claim_pending(session, 10)
    queue.mark_sent(session, rows, "batch_prov")
    monkeypatch.setattr("app.ai.batch.status", lambda batch_id: "completed")
    monkeypatch.setattr(
        "app.ai.batch.collect",
        lambda batch_id: [BatchResult(str(rows[0].id), _recorded_output(), None)],
    )

    scheduler.collect_once(session)

    stored: Evaluation | None = application.evaluation
    assert stored is not None
    assert stored.model_id == "gpt-5.6-luna"
    assert stored.prompt_version == "evaluator.v1"
    # The batch path must not skip the Python-side scoring (plan §6, layer 3).
    assert stored.overall_score > 0


def test_the_worker_is_off_unless_switched_on() -> None:
    """A loop that starts by accident spends real money."""
    from app.core.config import Settings

    assert Settings().worker_enabled is False
