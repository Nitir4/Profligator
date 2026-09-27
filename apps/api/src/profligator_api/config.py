from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Profligator API"
    environment: str = "development"
    database_url: str = "sqlite:///./profligator.db"
    auto_create_schema: bool = True
    codeforces_base_url: str = "https://codeforces.com/api"
    codeforces_min_interval_seconds: float = 2.05
    cors_origins: list[str] = ["http://localhost:5173"]
    sync_backend: Literal["inline", "rq"] = "inline"
    redis_url: str = "redis://localhost:6379/0"
    sync_queue_name: str = "profligator-syncs"
    sync_job_timeout_seconds: int = 300
    sync_max_attempts: int = 3
    sync_retry_base_seconds: float = 1.0
    auth_secret_key: str = "development-only-change-me-before-production"
    auth_issuer: str = "profligator-api"
    auth_audience: str = "profligator-web"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    auth_cookie_secure: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PROFLIGATOR_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_auth_settings(self) -> "Settings":
        if len(self.auth_secret_key) < 32:
            raise ValueError("PROFLIGATOR_AUTH_SECRET_KEY must contain at least 32 characters")
        if self.environment == "production" and self.auth_secret_key.startswith("development-"):
            raise ValueError("A production auth secret must be configured")
        if self.environment == "production" and not self.auth_cookie_secure:
            raise ValueError("Secure authentication cookies are required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
