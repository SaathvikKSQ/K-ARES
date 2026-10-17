"""Application settings.

All configuration is environment-driven (12-factor). See `.env.example` at the
repository root for the documented variable list. Never hardcode secrets here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """K-AERS runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # Application
    app_name: str = "K-AERS"
    version: str = "0.1.0"
    environment: str = "development"  # development | test | production
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite:///./kaers.db"
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Security / auth
    secret_key: str = "insecure-dev-secret-change-me"
    secret_encryption_key: str | None = None  # Fernet key; falls back to secret_key
    # Security / auth
    access_token_expire_minutes: int = 720
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Storage / uploads
    data_dir: str = "./data"
    max_upload_mb: int = 10
    max_dataset_rows: int = 20000

    # Outbound integration safety
    allow_private_targets: bool = False
    adapter_connect_timeout_s: float = 10.0
    adapter_read_timeout_s: float = 60.0
    adapter_max_response_bytes: int = 5_000_000

    # Retention (days)
    retention_days_artifacts: int = 90
    retention_days_exports: int = 7

    # Initial admin bootstrap (env-seeded; see specs/decisions.md D8 / open question 5)
    admin_email: str | None = None
    admin_password: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
