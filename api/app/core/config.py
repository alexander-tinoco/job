from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from the environment or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://screening:screening@localhost:5432/screening"
    openai_api_key: str = ""
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
