from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
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

    # Secrets are `SecretStr` so they render as `**********` everywhere a model
    # is printed — a traceback, a pytest assertion diff, a debug log. A pytest
    # failure once printed a live key into the terminal because a plain `str`
    # field is shown in full by the repr of the object holding it.
    openai_api_key: SecretStr = SecretStr("")
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
    resend_api_key: SecretStr = SecretStr("")
    outreach_from: str = ""

    # Observability.
    #
    # Traces are always recorded; they are only *exported* when an OTLP endpoint
    # is set, so an unconfigured deployment drops them at near-zero cost and
    # needs no collector to run.
    otel_endpoint: str = ""
    service_name: str = "verbatim-api"
    # JSON lines in production, human-readable text locally. A log nobody can
    # grep is not observability.
    log_json: bool = False
    log_level: str = "INFO"

    # /metrics is off unless a token is set, and then it wants that token. It
    # reports queue depth, spend and latency: useful to an operator, useful to
    # an attacker deciding when the system is busy enough not to be watched.
    metrics_token: SecretStr = SecretStr("")

    # Backlog past which readiness reports degraded. Not a failure: an instance
    # with a slow queue can still serve every page in the panel.
    queue_warning_minutes: int = 90

    # Résumé storage. The path is a root; files land under {root}/{application_id}/.
    uploads_dir: str = "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
