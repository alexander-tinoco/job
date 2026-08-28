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
    # Set to false only for local development over plain http. In any deployment
    # this must stay true: without it the session cookie travels in the clear.
    cookie_secure: bool = True

    # Where the panel lives. Configurable so a deployment can choose its own and
    # so it is never linked from the public site.
    #
    # This is not a security control and must not be treated as one. A URL leaks
    # through browser history, Referer headers, bookmarks and any chat someone
    # pastes it into. What protects the panel is the sign-in: Argon2, server-side
    # sessions, an HttpOnly cookie and a lockout. The path only keeps the admin
    # surface out of sight and out of search results.
    panel_path: str = "panel"
    environment: str = "development"

    # The background scheduler is off unless explicitly enabled. Failing closed:
    # a loop that starts by accident spends real money, and no test or script
    # should be able to trigger one (CLAUDE.md AI rule 12).
    worker_enabled: bool = False

    # Outreach. Unset means sending is unavailable and the API says so, rather
    # than accepting an approval and quietly dropping the message.
    resend_api_key: str = ""
    outreach_from: str = ""

    # Résumé storage. The path is a root; files land under {root}/{application_id}/.
    uploads_dir: str = "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
