from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from the environment or a local .env file."""

    # Resolved against the repository root, not the working directory: the API
    # is normally run from api/, where a relative ".env" would silently miss.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://screening:screening@localhost:5432/screening"
    openai_api_key: str = ""
    # Guards the private endpoints until real auth arrives in Phase 8.
    # Empty means "deny everything": failing closed is the safe default.
    admin_token: str = ""
    environment: str = "development"

    # The background scheduler is off unless explicitly enabled. Failing closed:
    # a loop that starts by accident spends real money, and no test or script
    # should be able to trigger one (CLAUDE.md AI rule 12).
    worker_enabled: bool = False

    # Résumé storage. The path is a root; files land under {root}/{application_id}/.
    uploads_dir: str = "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
