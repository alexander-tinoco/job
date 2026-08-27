from fastapi import FastAPI

from app.core.config import get_settings

app = FastAPI(title="Candidate Screening API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Reports the environment so deployments are identifiable."""
    return {"status": "ok", "environment": get_settings().environment}
