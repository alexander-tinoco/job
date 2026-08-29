"""Logs, traces and metrics.

Two duties here, and they pull apart. The system has to become legible to
whoever is on call — until now a stalled overnight batch left no trace anywhere
— without becoming legible to anyone else: metrics and logs are exactly where
personal data leaks by accident.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import observability
from app.core.config import get_settings
from app.db.models import JobQueue
from app.db.types import QueueState
from app.main import _queue_health


def _configure(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    """Set a setting for one test.

    Through the environment and the cache, not by patching the object: the
    client fixture clears `get_settings`, so an instance patched in a test is
    thrown away before the request is served.
    """
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


@pytest.fixture
def metrics_on(monkeypatch: pytest.MonkeyPatch) -> str:
    token = "test-scrape-token"
    _configure(monkeypatch, METRICS_TOKEN=token)
    return token


# --- The correlation id ---


def test_every_response_carries_a_correlation_id(client: TestClient) -> None:
    """The handle that gathers one request's log lines together."""
    response = client.get("/health")
    assert response.headers["X-Correlation-Id"]


def test_two_requests_get_different_ids(client: TestClient) -> None:
    first = client.get("/health").headers["X-Correlation-Id"]
    second = client.get("/health").headers["X-Correlation-Id"]
    assert first != second


def test_the_id_reaches_the_log_line(caplog: pytest.LogCaptureFixture) -> None:
    record = logging.LogRecord("t", logging.INFO, "f", 1, "hello", None, None)
    assert observability.CorrelationFilter().filter(record)
    assert record.correlation_id


# --- The JSON formatter ---


def test_a_log_line_is_one_json_object() -> None:
    record = logging.LogRecord("app.x", logging.WARNING, "f.py", 12, "queue stalled", None, None)
    record.correlation_id = "abc123"

    payload = json.loads(observability.JsonFormatter().format(record))

    assert payload["level"] == "WARNING"
    assert payload["logger"] == "app.x"
    assert payload["message"] == "queue stalled"
    assert payload["correlation_id"] == "abc123"


def test_extra_fields_survive_but_nothing_else_is_invented() -> None:
    """`extra=` is how an operator gets the application id onto the line."""
    record = logging.LogRecord("app.x", logging.INFO, "f.py", 1, "sent", None, None)
    record.application_id = "01a04b28-a41c-7567-86c5-ff7982b43b64"

    payload = json.loads(observability.JsonFormatter().format(record))

    assert payload["application_id"] == "01a04b28-a41c-7567-86c5-ff7982b43b64"
    # Nothing from the LogRecord's own machinery leaks into the line.
    assert "args" not in payload
    assert "msecs" not in payload
    assert "pathname" not in payload


def test_an_exception_is_carried_as_text() -> None:
    try:
        raise ValueError("batch collapsed")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "app.x", logging.ERROR, "f.py", 1, "failed", None, sys.exc_info()
        )
    payload = json.loads(observability.JsonFormatter().format(record))
    assert "batch collapsed" in payload["exception"]


# --- /metrics ---


def test_metrics_is_absent_until_a_token_is_configured(client: TestClient) -> None:
    """Failing closed, like the worker: unconfigured means unavailable, not open."""
    assert not get_settings().metrics_token.get_secret_value()
    assert client.get("/metrics").status_code == 404


def test_metrics_needs_the_token(client: TestClient, metrics_on: str) -> None:
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert (
        client.get("/metrics", headers={"Authorization": f"Bearer {metrics_on}"}).status_code == 200
    )


def test_metrics_reports_requests_by_route_template_not_by_path(
    client: TestClient, session: Session, metrics_on: str
) -> None:
    """A path label would mint a metric series per candidate — and leak the ids."""
    from tests.factories import make_opening

    opening = make_opening(session, slug="obs-route")
    session.commit()
    client.get(f"/openings/{opening.slug}")

    body = client.get("/metrics", headers={"Authorization": f"Bearer {metrics_on}"}).text

    assert 'route="/openings/{slug}"' in body
    assert "obs-route" not in body


def test_metrics_carries_the_numbers_a_bill_is_made_of(client: TestClient, metrics_on: str) -> None:
    observability.tokens_total.labels("input").inc(1187)
    observability.evaluations_total.labels("stored").inc()

    body = client.get("/metrics", headers={"Authorization": f"Bearer {metrics_on}"}).text

    assert "verbatim_tokens_total" in body
    assert "verbatim_evaluations_total" in body
    assert "verbatim_queue_depth" in body


# --- Readiness ---


def test_readiness_reports_the_queue_and_the_disk(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a healthy instance says.

    The threshold is pushed out of the way on purpose. Readiness opens its own
    connection rather than the test's, so it reads whatever is committed in the
    test database; the stalling rule is pinned by the test below, which puts a
    row of a known age there itself.
    """
    _configure(monkeypatch, OPENAI_API_KEY="sk-test", QUEUE_WARNING_MINUTES="100000")
    body = client.get("/ready").json()

    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["uploads"] == "ok"
    assert body["queue"]["stalled"] is False
    assert "oldest_pending_seconds" in body["queue"]


def test_an_old_backlog_reads_as_stalled(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """The rule itself, against the session that holds the row.

    Not through `/ready`: readiness opens its own connection, so a row written
    inside the test transaction is invisible to it. An earlier version of this
    test went through the endpoint and passed only because the local database
    still held stale rows from previous runs — on a clean CI database it failed.
    """
    _configure(monkeypatch, QUEUE_WARNING_MINUTES="90")
    old = datetime.now(UTC) - timedelta(minutes=120)
    session.add(JobQueue(task="evaluate", state=QueueState.PENDING, created_at=old))
    session.flush()

    reading = _queue_health(session)

    assert reading["stalled"] is True
    assert int(str(reading["oldest_pending_seconds"])) >= 120 * 60


def test_a_fresh_backlog_is_not_stalled(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Depth alone says nothing: a busy queue and a frozen one look identical."""
    _configure(monkeypatch, QUEUE_WARNING_MINUTES="90")
    session.add(JobQueue(task="evaluate", state=QueueState.PENDING))
    session.flush()

    reading = _queue_health(session)

    assert reading["stalled"] is False
    assert int(str(reading["depth"]["pending"])) >= 1  # type: ignore[index]


def test_a_stalled_queue_is_degraded_but_still_serving(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An instance with a frozen batch still serves every page in the panel.

    Returning 503 would let a background problem take the whole site out of
    rotation, which is a worse outage than the one being reported. The key is
    configured here so that `degraded` can only be coming from the queue.
    """
    _configure(monkeypatch, OPENAI_API_KEY="sk-test")
    monkeypatch.setattr(
        "app.main._queue_health",
        lambda _: {"depth": {"pending": 9}, "oldest_pending_seconds": 7200, "stalled": True},
    )

    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["queue"]["stalled"] is True
    assert body["database"] == "ok"
    assert body["model_api"] == "configured"


def test_readiness_never_calls_the_model_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe that spent money every time a platform polled it would be an incident."""
    _configure(monkeypatch, OPENAI_API_KEY="sk-test")
    assert client.get("/ready").json()["model_api"] == "configured"


def test_a_missing_model_key_reads_as_degraded(client: TestClient) -> None:
    """Applications would pile up unevaluated in silence. That is worth saying."""
    assert not get_settings().openai_api_key.get_secret_value()
    body = client.get("/ready").json()

    assert body["model_api"] == "unconfigured"
    assert body["status"] == "degraded"


def test_only_the_database_takes_the_instance_out_of_rotation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(*_: object, **__: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("app.main.SessionLocal", unreachable)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"


def test_the_servers_own_logging_is_taken_over(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uvicorn sets `propagate = False`, so the root handler alone changes nothing.

    Verified against the running stack, not in a unit test: with the root
    handler replaced and nothing else, `docker compose logs` still printed
    uvicorn's own plain-text lines.
    """
    _configure(monkeypatch, LOG_JSON="true")
    observability.configure_logging()

    for name in observability._UVICORN_LOGGERS:
        server = logging.getLogger(name)
        assert server.handlers == []
        assert server.propagate is True

    (handler,) = logging.getLogger().handlers
    assert isinstance(handler.formatter, observability.JsonFormatter)


def test_the_ansi_copy_of_a_server_message_is_dropped() -> None:
    record = logging.LogRecord("uvicorn.error", logging.INFO, "f", 1, "Running", None, None)
    record.color_message = "\x1b[1mRunning\x1b[0m"

    assert "color_message" not in json.loads(observability.JsonFormatter().format(record))
