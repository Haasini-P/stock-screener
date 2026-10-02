"""
StockMind AI — Application Configuration
Central configuration management using pydantic-settings.
All secrets are loaded from environment variables.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "StockMind AI"
    app_env: str = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # --- Upstox ---
    upstox_client_id: str = ""
    upstox_client_secret: str = ""
    upstox_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    upstox_analytics_token: Optional[str] = None
    upstox_api_base_url: str = "https://api.upstox.com"
    upstox_sandbox_base_url: str = "https://sandbox.upstox.com"
    upstox_ws_base_url: str = "wss://api.upstox.com"

    # --- Zerodha Kite Connect ---
    # Kite has no per-request redirect param — kite_redirect_uri is reference-only:
    # register this exact URL as the fixed redirect URL in the Kite Developer Console.
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_redirect_uri: str = "http://localhost:8000/api/auth/kite/callback"

    # --- Trailing stop-loss monitor (Kite only — Upstox trails natively via GTT) ---
    trailing_poll_seconds: int = 60

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./stockmind.db"
    database_url_sync: str = "sqlite:///./stockmind.db"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_url: str = "redis://localhost:6379/1"
    redis_celery_url: str = "redis://localhost:6379/2"

    # --- Security ---
    jwt_secret: str = "change-this-to-a-random-64-char-string"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440
    encryption_key: str = "change-this-to-a-fernet-key"

    # --- ML ---
    model_registry_path: str = "./model_registry"
    model_version: str = "v1.0.0"
    ml_training_lookback_days: int = 750

    # --- Celery ---
    celery_broker_url: str = "redis://localhost:6379/2"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- Logging ---
    log_level: str = "INFO"
    log_format: str = "json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def upstox_base_url(self) -> str:
        """Return sandbox URL in development, production URL otherwise."""
        if self.is_development and not self.upstox_client_id:
            return self.upstox_sandbox_base_url
        return self.upstox_api_base_url

    @property
    def has_upstox_credentials(self) -> bool:
        return bool(self.upstox_client_id and self.upstox_client_secret)

    @property
    def has_kite_credentials(self) -> bool:
        return bool(self.kite_api_key and self.kite_api_secret)


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
