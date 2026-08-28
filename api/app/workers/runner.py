"""The background loop: collect hourly, send on the schedule.

Runs inside the API process rather than as a separate service. With batches
every six hours the load is negligible, and one container on Railway instead of
two is a real saving at this size (plan §2). Splitting it out later is moving a
file, not a redesign.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from app.db.session import SessionLocal
from app.services import lifecycle
from app.services.queue import now
from app.workers import scheduler

logger = logging.getLogger(__name__)

TICK_SECONDS = 3600


def tick() -> None:
    """One pass: collect what has finished, expire what never will, then send."""
    with SessionLocal() as session:
        try:
            stored = scheduler.collect_once(session)
            expired = scheduler.expire_stale(session)
            outcome = scheduler.send_once(session, now().hour)
            # Retention runs on the same tick. "Deleted after six months" is a
            # claim on the application page, so nothing may depend on a person
            # remembering to press a button.
            swept = lifecycle.sweep(session)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("scheduler_tick_failed")
            return
    if stored or expired or outcome.sent or swept.applications:
        logger.info(
            "scheduler_tick collected=%s expired=%s sent=%s skipped=%s retained_deleted=%s",
            stored,
            expired,
            outcome.sent,
            outcome.skipped,
            swept.applications,
        )


async def run_forever(interval: int = TICK_SECONDS) -> None:
    while True:
        await asyncio.to_thread(tick)
        await asyncio.sleep(interval)


@contextlib.asynccontextmanager
async def lifespan_task(interval: int = TICK_SECONDS):  # type: ignore[no-untyped-def]
    """Start the loop with the app and cancel it cleanly on shutdown."""
    task = asyncio.create_task(run_forever(interval))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
