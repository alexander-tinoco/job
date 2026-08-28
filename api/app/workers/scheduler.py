"""Two jobs, deliberately separate: sending and collecting (plan §4.1).

Sending runs every six hours, or sooner when applications pile up. Collecting
runs hourly, because a batch can finish at any point inside a 24-hour window and
scores should appear when they are ready rather than at the next send slot.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.ai import batch
from app.db.models import Application, JobQueue
from app.db.types import QueueState
from app.services import queue
from app.services.evaluation import build_request, persist_evaluation

logger = logging.getLogger(__name__)

SEND_HOURS = (0, 6, 12, 18)
# Send early once this many applications are waiting. Covers the day a LinkedIn
# post works and 200 arrive in three hours; without it HR waits up to six.
PENDING_TRIGGER = 50
MAX_ITEMS_PER_BATCH = 200

# Starting guess for the enqueued-token ceiling. Not read from a dashboard and
# not a constant to trust: the real limit depends on the account's usage tier
# and changes as the account spends. `remember_limit` narrows it from what the
# API actually rejects, which stays correct across tier changes.
DEFAULT_TOKEN_BUDGET = 80_000
MIN_TOKEN_BUDGET = 5_000

_token_budget = DEFAULT_TOKEN_BUDGET


def token_budget() -> int:
    return _token_budget


def remember_limit(attempted: int) -> None:
    """Halve the working budget after a rejection, with a floor."""
    global _token_budget
    _token_budget = max(MIN_TOKEN_BUDGET, attempted // 2)
    logger.warning("enqueued_token_limit_hit attempted=%s new_budget=%s", attempted, _token_budget)


def reset_budget() -> None:
    global _token_budget
    _token_budget = DEFAULT_TOKEN_BUDGET


@dataclass(frozen=True)
class SendOutcome:
    batch_id: str | None
    sent: int
    skipped: int


def should_send(hour: int, pending: int) -> bool:
    if pending == 0:
        return False
    return hour in SEND_HOURS or pending >= PENDING_TRIGGER


def _items(session: Session, rows: list[JobQueue]) -> list[tuple[JobQueue, batch.BatchItem]]:
    """Pair queue rows with their request, dropping rows that cannot be built."""
    pairs: list[tuple[JobQueue, batch.BatchItem]] = []
    for row in rows:
        if row.application_id is None:
            queue.mark_failed(session, row, "queue row has no application")
            continue
        application = session.get(Application, row.application_id)
        if application is None:
            queue.mark_failed(session, row, "application no longer exists")
            continue
        try:
            request = build_request(application)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the send
            queue.mark_failed(session, row, f"{type(exc).__name__}: {exc}")
            continue
        pairs.append((row, batch.BatchItem(custom_id=str(row.id), request=request)))
    return pairs


def fit_to_budget(
    pairs: list[tuple[JobQueue, batch.BatchItem]], budget: int
) -> list[tuple[JobQueue, batch.BatchItem]]:
    """Take the longest prefix that fits the enqueued-token budget.

    A prefix rather than a best fit: the queue is ordered oldest first and
    candidates should be evaluated in the order they applied.
    """
    chosen: list[tuple[JobQueue, batch.BatchItem]] = []
    used = 0
    for row, item in pairs:
        size = batch.estimate_input_tokens([item])
        if chosen and used + size > budget:
            break
        chosen.append((row, item))
        used += size
    return chosen


def send_once(session: Session, hour: int) -> SendOutcome:
    """Build and submit one sub-batch. Called again next tick for the remainder."""
    pending = queue.count_pending(session)
    if not should_send(hour, pending):
        return SendOutcome(batch_id=None, sent=0, skipped=pending)

    rows = queue.claim_pending(session, MAX_ITEMS_PER_BATCH)
    pairs = _items(session, rows)
    if not pairs:
        return SendOutcome(batch_id=None, sent=0, skipped=0)

    chosen = fit_to_budget(pairs, token_budget())
    try:
        batch_id = batch.submit([item for _, item in chosen])
    except Exception as exc:  # noqa: BLE001 - the API is the only source of the real limit
        if _looks_like_a_limit(exc):
            remember_limit(batch.estimate_input_tokens([item for _, item in chosen]))
            session.rollback()
            return SendOutcome(batch_id=None, sent=0, skipped=len(pairs))
        raise

    queue.mark_sent(session, [row for row, _ in chosen], batch_id)
    logger.info("batch_sent batch_id=%s items=%s", batch_id, len(chosen))
    return SendOutcome(batch_id=batch_id, sent=len(chosen), skipped=pending - len(chosen))


def _looks_like_a_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return "token" in text and ("limit" in text or "enqueued" in text or "exceed" in text)


def collect_once(session: Session) -> int:
    """Read every finished batch and persist what came back."""
    stored = 0
    for batch_id in queue.sent_batches(session):
        state = batch.status(batch_id)
        if state in {"validating", "in_progress", "finalizing"}:
            continue
        if state in {"failed", "expired", "cancelled"}:
            for row in queue.rows_for_batch(session, batch_id).values():
                queue.mark_failed(session, row, f"batch {state}")
            continue

        rows = queue.rows_for_batch(session, batch_id)
        for result in batch.collect(batch_id):
            # Keyed by custom_id, never by position: results come back unordered.
            key = _as_uuid(result.custom_id)
            matched = rows.get(key) if key is not None else None
            if matched is None:
                logger.warning(
                    "batch_result_unmatched batch_id=%s id=%s", batch_id, result.custom_id
                )
                continue
            if result.output is None or matched.application_id is None:
                queue.mark_failed(session, matched, result.error or "no output")
                continue
            application = session.get(Application, matched.application_id)
            if application is None:
                queue.mark_failed(session, matched, "application no longer exists")
                continue
            persist_evaluation(session, application, result.output)
            queue.mark_done(session, matched)
            stored += 1

        for row in rows.values():
            if row.state is QueueState.SENT:
                queue.mark_failed(session, row, "missing from batch output")
    return stored


def expire_stale(session: Session) -> int:
    """Fail rows sent more than a day ago. The window is 24 h and fixed."""
    cutoff = queue.now() - timedelta(hours=25)
    stale = queue.stale_sent(session, cutoff)
    for row in stale:
        queue.mark_failed(session, row, "batch did not return within the 24h window")
    return len(stale)


def _as_uuid(value: str) -> uuid.UUID | None:
    """custom_id is our own queue-row id, but a malformed one must not crash the run."""
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
