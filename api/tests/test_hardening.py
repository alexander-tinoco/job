"""Regression tests for the inspection findings.

Each one pins a defect that measurement found, so it cannot come back quietly.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.ai.evaluator import load_prompt
from app.core.config import get_settings
from app.db.models import Application, ResumeDocument
from app.services import queue, storage
from tests.factories import make_application, make_opening


def test_the_prompt_is_read_from_disk_only_once() -> None:
    """A batch of 200 was reading the same immutable file 400 times."""
    load_prompt.cache_clear()
    reads = {"n": 0}
    original = Path.read_text

    def counted(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix == ".md":
            reads["n"] += 1
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    Path.read_text = counted  # type: ignore[method-assign]
    try:
        for _ in range(50):
            load_prompt()
    finally:
        Path.read_text = original  # type: ignore[method-assign]

    assert reads["n"] == 1


def test_building_a_batch_costs_the_same_whatever_its_size(session: Session) -> None:
    """This was 3.1 queries per application: the row, its opening, its criteria.

    Asserted as flatness rather than an absolute count: what matters is that a
    200-item batch does not cost forty times a 5-item one.
    """
    from app.workers import scheduler

    def queries_for(count: int, slug: str) -> int:
        opening = make_opening(session, slug=slug)
        for index in range(count):
            application = make_application(session, opening, f"{slug}-{index}@example.com")
            application.resume = ResumeDocument(
                storage_path=f"{application.id}/cv.pdf", visible_text="Python and SQL " * 30
            )
            queue.enqueue(session, application)
        session.flush()
        rows = [r for r in queue.claim_pending(session, 500) if r.batch_id is None]

        counted = {"n": 0}
        engine = session.get_bind()

        def count(*args: object, **kwargs: object) -> None:
            counted["n"] += 1

        event.listen(engine, "before_cursor_execute", count)
        try:
            pairs = scheduler._items(session, rows)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert len(pairs) == len(rows)
        queue.mark_sent(session, rows, f"batch-{slug}")
        return counted["n"]

    small = queries_for(5, "flat-small")
    large = queries_for(40, "flat-large")

    # One query per table, not per candidate: applications, openings, criteria,
    # résumés. Eight times the work must not mean eight times the queries.
    assert large <= small + 1, f"{small} queries for 5, {large} for 40"


def test_pending_is_counted_in_the_database(session: Session) -> None:
    """Fetching every id to call len() moves rows just to learn a number."""
    opening = make_opening(session, slug="count-check")
    for index in range(3):
        queue.enqueue(session, make_application(session, opening, f"c{index}@example.com"))
    session.flush()

    counted = {"n": 0}
    engine = session.get_bind()

    def count(*args: object, **kwargs: object) -> None:
        counted["n"] += 1

    event.listen(engine, "before_cursor_execute", count)
    try:
        total = queue.count_pending(session)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert total == 3
    assert counted["n"] == 1


def test_deleting_a_resume_removes_the_file(client: TestClient, session: Session) -> None:
    """A cascading delete clears the rows and leaves the PDF on disk."""
    from tests.pdfs import make_resume

    make_opening(session, slug="delete-check")
    session.commit()
    client.post(
        "/openings/delete-check/apply",
        data={"full_name": "Ada", "email": "del@example.com", "consent": "true"},
        files={"resume": ("cv.pdf", make_resume(), "application/pdf")},
    )
    application = session.scalar(__import__("sqlalchemy").select(Application))
    assert application is not None and application.resume is not None
    path = Path(get_settings().uploads_dir) / application.resume.storage_path
    assert path.exists()

    assert storage.delete_resume(application.resume.storage_path) is True
    assert not path.exists()


def test_deleting_refuses_to_escape_the_uploads_directory() -> None:
    import pytest

    with pytest.raises(storage.InvalidUploadError):
        storage.delete_resume("../../etc/passwd")


def test_health_is_cheap_and_ready_checks_the_database(client: TestClient) -> None:
    """A liveness probe that queries the database restarts the app on a blip."""
    assert client.get("/health").json()["status"] == "ok"

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"
