import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api.v1 import applications, evaluations, openings, public
from app.core.config import get_settings
from app.workers.runner import run_forever


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
app.include_router(openings.router)
app.include_router(public.router)
app.include_router(applications.router)
app.include_router(evaluations.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Reports the environment so deployments are identifiable."""
    return {"status": "ok", "environment": get_settings().environment}
