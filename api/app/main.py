from fastapi import FastAPI

from app.api.v1 import applications, evaluations, openings, public
from app.core.config import get_settings

app = FastAPI(title="Candidate Screening API")
app.include_router(openings.router)
app.include_router(public.router)
app.include_router(applications.router)
app.include_router(evaluations.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Reports the environment so deployments are identifiable."""
    return {"status": "ok", "environment": get_settings().environment}
