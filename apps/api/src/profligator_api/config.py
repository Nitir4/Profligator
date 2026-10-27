from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from urllib.parse import urlparse
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
    public_web_url: str = "http://localhost:5173"
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_redirect_uri: str | None = None
    password_reset_email_backend: Literal["disabled", "smtp"] = "disabled"
    password_reset_minutes: int = Field(default=15, ge=5, le=60)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl", "plain"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_from_email: EmailStr | None = None
    smtp_timeout_seconds: float = Field(default=10, gt=0, le=30)
    verification_email_backend: Literal["disabled", "smtp"] = "disabled"
    verification_smtp_host: str = "smtp.gmail.com"
    verification_smtp_port: int = Field(default=587, ge=1, le=65535)
    verification_smtp_security: Literal["starttls", "ssl", "plain"] = "starttls"
    verification_smtp_username: str = ""
    verification_smtp_password: SecretStr | None = None
    verification_smtp_from_email: EmailStr | None = None
    sync_interval_seconds: int = Field(default=21600, ge=60)
    profile_sync_cooldown_seconds: int = Field(default=900, ge=0)
    scheduler_poll_seconds: int = Field(default=60, ge=1)
    matching_backend: Literal["disabled", "ollama", "groq"] = "disabled"
    groq_api_key: SecretStr | None = None
    groq_min_interval_seconds: float = Field(default=2.1, ge=0)
    groq_max_completion_tokens: int = Field(default=2048, ge=256, le=8192)
    groq_max_input_chars: int = Field(default=16000, ge=1000, le=100000)
    extension_session_days: int = Field(default=30, ge=1, le=90)
    extension_history_cooldown_seconds: int = Field(default=60, ge=0)
    matching_base_url: str = "http://localhost:11434"
    matching_model: str = ""
    matching_timeout_seconds: float = Field(default=30, gt=0)
    matching_min_confidence: float = Field(default=0.95, ge=0.9, le=1)
    matching_candidate_limit: int = Field(default=8, ge=1, le=50)
    matching_max_comparisons: int = Field(default=64, ge=1, le=1000)
    matching_run_timeout_seconds: float = Field(default=60, gt=0)
    matching_check_timeout_seconds: float = Field(default=10, gt=0)
    aggregation_service_url: str | None = None
    leetcode_connector: Literal["scraper", "fixture"] = "scraper"
    leetcode_collect_contests: bool = False
    geeksforgeeks_connector: Literal["scraper", "fixture"] = "scraper"
    scraper_min_interval_seconds: float = Field(default=2.05, ge=1)
    scraper_statement_limit: int = Field(default=20, ge=0, le=50)
    scraper_calendar_year_limit: int = Field(default=3, ge=1, le=10)

    model_config = SettingsConfigDict(
        env_file=(".env", Path(__file__).resolve().parents[2] / ".env"),
        env_prefix="PROFLIGATOR_",
        extra="ignore",
    )

    @field_validator("smtp_from_email", "verification_smtp_from_email", mode="before")
    @classmethod
    def empty_smtp_sender(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_auth_settings(self) -> "Settings":
        if self.verification_email_backend == "smtp":
            self.verification_mail_settings().validate_auth_settings()
        if self.password_reset_email_backend == "smtp":
            if not self.smtp_host.strip() or not self.smtp_from_email:
                raise ValueError("SMTP host and sender email are required for password recovery")
            if bool(self.smtp_username) != bool(self.smtp_password and self.smtp_password.get_secret_value()):
                raise ValueError("Configure both SMTP username and SMTP password")
            if self.smtp_security == "plain" and (self.environment == "production" or self.smtp_host not in {"localhost", "127.0.0.1", "::1"}):
                raise ValueError("Plain SMTP is only allowed for local development mail servers")
            uri = urlparse(self.public_web_url)
            if (not uri.hostname or uri.username or uri.password or uri.query or uri.fragment or uri.path not in {"", "/"}
                    or (uri.scheme != "https" and not (self.environment != "production" and uri.scheme == "http"
                        and uri.hostname in {"localhost", "127.0.0.1", "::1"}))):
                raise ValueError("Password reset links require an HTTPS web origin or localhost HTTP in development")
        if self.google_enabled:
            uri = urlparse(self.google_callback_url)
            if (not uri.hostname or uri.username or uri.password or uri.query or uri.fragment
                    or (uri.scheme != "https" and not (
                        self.environment != "production" and uri.scheme == "http"
                        and uri.hostname in {"localhost", "127.0.0.1", "::1"}
                    ))):
                raise ValueError("Google redirect URI must use HTTPS, or localhost HTTP in development")
        if self.matching_backend == "ollama" and not self.matching_model.strip():
            raise ValueError("PROFLIGATOR_MATCHING_MODEL is required for Ollama matching")
        if self.matching_backend == "groq":
            if not self.groq_api_key or not self.groq_api_key.get_secret_value().strip():
                raise ValueError("PROFLIGATOR_GROQ_API_KEY is required for Groq matching")
            if not self.matching_model.strip():
                self.matching_model = "openai/gpt-oss-120b"
        if len(self.auth_secret_key) < 32:
            raise ValueError("PROFLIGATOR_AUTH_SECRET_KEY must contain at least 32 characters")
        if self.environment == "production" and self.auth_secret_key.startswith("development-"):
            raise ValueError("A production auth secret must be configured")
        if self.environment == "production" and not self.auth_cookie_secure:
            raise ValueError("Secure authentication cookies are required in production")
        return self

    def verification_mail_settings(self) -> "Settings":
        return self.model_copy(update={
            "verification_email_backend": "disabled",
            "password_reset_email_backend": self.verification_email_backend,
            **{f"smtp_{name}": getattr(self, f"verification_smtp_{name}") for name in
               ("host", "port", "security", "username", "password", "from_email")},
        })

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.google_client_secret.get_secret_value())

    @property
    def google_callback_url(self) -> str:
        return self.google_redirect_uri or f"{self.public_web_url.rstrip('/')}/api/v1/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
