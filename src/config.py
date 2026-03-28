from functools import lru_cache

from pydantic import AmqpDsn, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All fields without default values are required in .env file.
    Fields with defaults are optional and fall back to provided values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Database ---
    database_url: PostgresDsn

    # --- Redis ---
    redis_url: RedisDsn

    # --- RabbitMQ ---
    rabbitmq_url: AmqpDsn

    # --- JWT ---
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    # --- SMTP ---
    smtp_host: str = "localhost"
    smtp_port: int = 1025

    # --- Telegram ---
    telegram_bot_token: str = ""

    # --- Rate limiting ---
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton.

    Uses lru_cache so .env is read only once per process.
    In tests, call get_settings.cache_clear() to reset.
    """
    return Settings()


settings: Settings = get_settings()
