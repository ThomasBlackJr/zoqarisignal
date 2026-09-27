from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.db import database_url


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = Field(default="sqlite:///./data/drive.db", repr=False)
    environment: Literal["development", "production"] = "development"
    vercel: bool = False

    @model_validator(mode="after")
    def persistent_database(self):
        if self.vercel and self.environment != "production":
            raise ValueError("Vercel requires explicit ENVIRONMENT=production")
        url = database_url(self.database_url)
        if self.environment == "production" and (
            url.drivername != "postgresql+psycopg" or not url.host or not url.database
        ):
            raise ValueError(
                "Production requires an explicit persistent PostgreSQL DATABASE_URL with host and database"
            )
        self.database_url = url.render_as_string(hide_password=False)
        return self


class Settings(DatabaseSettings):
    upload_dir: Path = Path("./data/audio")
    frontend_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    session_hours: int = Field(default=12, ge=1, le=168)
    max_upload_mb: int = Field(default=24, ge=1, le=24)
    transcription_provider: Literal["demo", "openai"] = "demo"
    qa_provider: Literal["demo", "openai"] = "demo"
    openai_api_key: str = ""
    transcription_model: str = "whisper-1"
    qa_model: str = "gpt-4o-mini"
    worker_enabled: bool = True
    dev_entitlements_enabled: bool = False
    mail_delivery: Literal["disabled", "local", "smtp"] = "disabled"
    mail_outbox_dir: Path = Path("./data/mail-outbox")
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    mail_from: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_mode: Literal["test", "live"] = "test"
    stripe_price_starter_month: str = ""
    stripe_price_starter_year: str = ""
    stripe_price_business_month: str = ""
    stripe_price_business_year: str = ""
    stripe_price_pro_month: str = ""
    stripe_price_pro_year: str = ""

    @model_validator(mode="after")
    def credentials(self):
        if self.vercel:
            raise ValueError(
                "Vercel recording storage is not implemented: the current backend requires persistent local audio "
                "storage and a long-running worker host. PostgreSQL alone does not satisfy these requirements."
            )
        if self.stripe_secret_key and not self.stripe_secret_key.startswith("sk_" + self.stripe_mode + "_"):
            raise ValueError("Stripe key must match STRIPE_MODE")
        if self.environment == "development" and self.stripe_mode != "test":
            raise ValueError("Development billing requires Stripe test mode")
        local_tools = self.dev_entitlements_enabled or self.mail_delivery == "local"
        if local_tools and (
            self.environment != "development"
            or urlparse(self.frontend_origin).hostname not in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("Development mail/entitlements require development mode and a loopback frontend")
        if self.environment == "production" and (
            not self.cookie_secure or not self.frontend_origin.startswith("https://") or self.mail_delivery != "smtp"
        ):
            raise ValueError("Production requires HTTPS, secure cookies and configured SMTP delivery")
        if self.mail_delivery == "smtp" and (not self.smtp_host or not self.mail_from):
            raise ValueError("SMTP_HOST and MAIL_FROM are required for SMTP delivery")
        if "openai" in (self.transcription_provider, self.qa_provider) and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI providers")
        if self.qa_provider == "demo" and self.transcription_provider != "demo":
            raise ValueError("Demo QA requires demo transcription; configure both providers for real calls")
        return self
