"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by the bot and the web app."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: str = ""

    # Database
    database_url: str = "postgresql+psycopg://shopping:shopping@db:5432/shopping"

    # Web
    web_base_url: str = "http://localhost:8000"
    web_host: str = "0.0.0.0"
    web_port: int = 8000

    # Defaults
    default_currency: str = "USD"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
