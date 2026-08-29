import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from hmac import compare_digest
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.v1 import (
    applications,
    auth,
    compare,
    duplicates,
    evaluations,
    lifecycle,
    openings,
    outreach,
    panel,
    public,
    sharing,
)
from app.core import observability
from app.core.config import get_settings
from app.db.models import JobQueue
from app.db.session import SessionLocal, engine
from app.db.types import QueueState
from app.workers.runner import run_forever

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run the batch scheduler alongside the API, when it is switched on."""
    observability.configure_logging()
    observability.configure_tracing()
    if not SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry:
        SQLAlchemyInstrumentor().instrument(engine=engine)
    if not get_settings().worker_enabled:
        yield
        return
    import asyncio

    task = asyncio.create_task(run_forever())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Candidate Screening API", lifespan=lifespan)


FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,metrics")


@app.middleware("http")
async def record_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Time every request, count it, and hand the caller its correlation id.

    The route *template* is the label, never the path: `/applications/{id}` as a
    label would mint one metric series per candidate and leak ids into the
    metrics endpoint at the same time.
    """
    with observability.Timer() as timer:
        response = await call_next(request)

    route = request.scope.get("route")
    template = getattr(route, "path", "unmatched")
    method = request.method
    observability.requests_total.labels(method, template, str(response.status_code)).inc()
    observability.request_seconds.labels(method, template).observe(timer.seconds)
    response.headers["X-Correlation-Id"] = observability.correlation_id()
    return response


app.include_router(auth.router)
app.include_router(openings.router)
app.include_router(public.router)
app.include_router(applications.router)
app.include_router(evaluations.router)
app.include_router(panel.router)
app.include_router(outreach.router)
app.include_router(lifecycle.router)
app.include_router(sharing.router)
app.include_router(compare.router)
app.include_router(duplicates.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only. Always cheap, never touches the database."""
    return {"status": "ok", "environment": get_settings().environment}


@app.get("/ready")
def ready(response: Response) -> dict[str, object]:
    """Readiness: is this instance actually able to serve?

    Separate from /health on purpose. A liveness probe that queries the database
    restarts the app when the database blips; a readiness probe that does not is
    useless, because the platform keeps routing traffic to an instance that can
    do nothing.

    **Only the database returns 503.** A stalled queue or a full disk is worth
    knowing about and is reported here, but an instance with a slow batch still
    serves every page in the panel — pulling it out of rotation would turn a
    background problem into an outage. Those come back `degraded`, at 200.

    The model API is reported as *configured or not*, never called. A readiness
    probe that spent money every time a platform polled it would be its own
    incident.
    """
    checks: dict[str, object] = {}
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            checks["database"] = "ok"
            checks["queue"] = _queue_health(session)
    except Exception:
        logger.exception("readiness_check_failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "unreachable"}

    checks["uploads"] = "ok" if _uploads_writable() else "unwritable"
    configured = bool(get_settings().openai_api_key.get_secret_value())
    checks["model_api"] = "configured" if configured else "unconfigured"

    degraded = [name for name, value in checks.items() if _is_degraded(value)]
    checks["status"] = "degraded" if degraded else "ready"
    return checks


def _is_degraded(value: object) -> bool:
    if isinstance(value, dict):
        return bool(value.get("stalled"))
    return value not in {"ok", "configured"}


def _queue_health(session: Session) -> dict[str, object]:
    """Depth by state and the age of the oldest waiting row.

    The oldest row is the number that says a batch stalled: depth alone looks
    identical whether work is flowing or frozen.
    """
    depths = {
        str(state): int(count)
        for state, count in session.execute(
            select(JobQueue.state, func.count()).group_by(JobQueue.state)
        )
    }
    for state in QueueState:
        observability.queue_depth.labels(str(state)).set(depths.get(str(state), 0))

    oldest = session.scalar(
        select(func.min(JobQueue.created_at)).where(JobQueue.state == QueueState.PENDING)
    )
    age = (datetime.now(UTC) - oldest).total_seconds() if oldest else 0.0
    observability.queue_oldest_seconds.set(age)

    limit = get_settings().queue_warning_minutes * 60
    return {"depth": depths, "oldest_pending_seconds": int(age), "stalled": age > limit}


def _uploads_writable() -> bool:
    try:
        root = Path(get_settings().uploads_dir)
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".readiness"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return False
    return True


@app.get("/metrics")
def metrics(authorization: str = Header(default="")) -> Response:
    """Prometheus exposition, off unless a token is configured.

    Queue depth, spend and latency tell an operator what is happening and tell
    an attacker when nobody is looking. Failing closed is the same choice the
    worker makes: unconfigured means unavailable, not open.
    """
    expected = get_settings().metrics_token.get_secret_value()
    if not expected:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found.")
    if not compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authorised.")
    return Response(generate_latest(observability.REGISTRY), media_type=CONTENT_TYPE_LATEST)
