"""The background loop.

One tick does five things and any of them can fail. What matters is not that
each works — the scheduler's own tests cover that — but that a failure in one
does not take the others down with it, and that the tick never leaves a half
written transaction behind.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from sqlalchemy.orm import Session

from app.workers import runner


class _NoClose:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *_: object) -> None:
        pass


@pytest.fixture
def tick_session(session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    """The tick opens its own session against `DATABASE_URL`; borrow the test's."""
    monkeypatch.setattr(runner, "SessionLocal", lambda: _NoClose(session))
    return session


def _stub(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> dict[str, int]:
    """Replace the tick's five pieces of work with counters."""
    calls = {"collect": 0, "expire": 0, "send": 0, "sweep": 0, "throttles": 0}

    def counted(name: str, result: object):
        def run(*_: object, **__: object) -> object:
            calls[name] += 1
            return result

        return overrides.get(name) or run

    monkeypatch.setattr(runner.scheduler, "collect_once", counted("collect", 0))
    monkeypatch.setattr(runner.scheduler, "expire_stale", counted("expire", 0))
    monkeypatch.setattr(
        runner.scheduler,
        "send_once",
        counted("send", runner.scheduler.SendOutcome(batch_id=None, sent=0, skipped=0)),
    )
    monkeypatch.setattr(runner.lifecycle, "sweep", counted("sweep", runner.lifecycle.Swept()))
    monkeypatch.setattr(runner.limits, "sweep", counted("throttles", 0))
    return calls


def test_one_tick_does_all_five_pieces_of_work(
    tick_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub(monkeypatch)

    runner.tick()

    assert calls == {"collect": 1, "expire": 1, "send": 1, "sweep": 1, "throttles": 1}


def test_a_failure_rolls_back_rather_than_leaving_half_a_tick(
    tick_session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Retention must not be committed by a tick whose collect blew up."""
    rolled: list[str] = []
    monkeypatch.setattr(tick_session, "rollback", lambda: rolled.append("rollback"))

    def boom(*_: object, **__: object) -> int:
        raise RuntimeError("the batch API is down")

    _stub(monkeypatch, collect=boom)

    with caplog.at_level(logging.ERROR):
        runner.tick()

    assert rolled == ["rollback"]
    assert "scheduler_tick_failed" in caplog.text
    # The exception is swallowed on purpose: the loop must survive to try again.


def test_a_quiet_tick_says_nothing(
    tick_session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An hourly loop that logged every idle pass would bury the real ones."""
    _stub(monkeypatch)

    with caplog.at_level(logging.INFO, logger="app.workers.runner"):
        runner.tick()

    assert [r for r in caplog.records if r.name == "app.workers.runner"] == []


def test_a_tick_that_did_something_says_what(
    tick_session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _stub(monkeypatch, collect=lambda *_: 3)

    with caplog.at_level(logging.INFO, logger="app.workers.runner"):
        runner.tick()

    (record,) = [r for r in caplog.records if r.name == "app.workers.runner"]
    assert "collected=3" in record.getMessage()


async def test_the_loop_keeps_ticking(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = 0

    def counted() -> None:
        nonlocal ticks
        ticks += 1

    monkeypatch.setattr(runner, "tick", counted)
    task = asyncio.create_task(runner.run_forever(interval=0))
    await asyncio.sleep(0.05)
    task.cancel()

    assert ticks > 1


async def test_shutdown_cancels_the_loop_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cancelled task that is never awaited leaves a warning on shutdown."""
    monkeypatch.setattr(runner, "tick", lambda: None)

    async with runner.lifespan_task(interval=0):
        await asyncio.sleep(0.01)

    # Leaving the context must not raise: the cancellation is caught inside.
