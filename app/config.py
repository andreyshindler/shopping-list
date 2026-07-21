"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by the bot and the web app."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: str = ""
    # Owner's numeric Telegram ID. Receives new-user notifications and is
    # auto-approved. While 0 (unset), the approval gate is disabled.
    admin_telegram_id: int = 0

    # Database
    database_url: str = "postgresql+psycopg://shopping:shopping@db:5432/shopping"

    # Web
    web_base_url: str = "http://localhost:8000"
    web_host: str = "0.0.0.0"
    web_port: int = 8000

    # Defaults
    default_currency: str = "ILS"

    # Receipt scanning (Claude vision). When anthropic_api_key is empty the bot's
    # "Scan receipt" feature is disabled and replies that it isn't configured.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    # Global price feed (Shufersal). Used by the daily app.jobs.fetch_prices job that
    # populates the shared global_products catalog.
    shufersal_store_id: str = "7290027600007"
    price_fetch_max_files: int = 5
    global_price_currency: str = "ILS"
    # Skip TLS verification for the price feed. Off by default (production stays
    # secure); enable only on networks with TLS interception (e.g. a local proxy).
    price_fetch_insecure: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
