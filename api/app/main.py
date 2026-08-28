import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Response, status
from sqlalchemy import text

from app.api.v1 import applications, auth, evaluations, openings, panel, public
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.workers.runner import run_forever

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run the batch scheduler alongside the API, when it is switched on."""
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
app.include_router(auth.router)
app.include_router(openings.router)
app.include_router(public.router)
app.include_router(applications.router)
app.include_router(evaluations.router)
app.include_router(panel.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only. Always cheap, never touches the database."""
    return {"status": "ok", "environment": get_settings().environment}


@app.get("/ready")
def ready(response: Response) -> dict[str, str]:
    """Readiness: is this instance actually able to serve?

    Separate from /health on purpose. A liveness probe that queries the database
    restarts the app when the database blips; a readiness probe that does not is
    useless, because the platform keeps routing traffic to an instance that can
    do nothing.
    """
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readiness_check_failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "unreachable"}
    return {"status": "ready", "database": "ok"}
