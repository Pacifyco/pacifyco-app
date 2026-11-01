from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# One .env for the whole repo, at the root (see README). Real environment variables win over it.
ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

LOCAL_WEB_ORIGIN = "http://localhost:5173"
# The Docker Compose database (docker-compose.yml). Used only when ENVIRONMENT is local and DATABASE_URL is blank.
LOCAL_DATABASE_URL = "postgresql+psycopg://pacifyco:pacifyco@localhost:5432/pacifyco"


class Environment(StrEnum):
    local = "local"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    environment: Environment = Environment.local
    database_url: str = ""
    supabase_url: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str = ""
    resend_api_key: str = ""
    email_from: str = ""
    admin_alert_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    google_service_account_json: str = ""
    google_calendar_id: str = ""
    sentry_dsn: str = ""
    jobs_secret: str = ""
    public_web_url: str = ""
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    pacify_upi_id: str = ""

    @field_validator("environment", mode="before")
    @classmethod
    def _blank_environment_is_local(cls, value: object) -> object:
        return value or Environment.local

    @field_validator("admin_alert_emails", "cors_origins", mode="before")
    @classmethod
    def _split_comma_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must list our web origins; '*' is not allowed")
        return [origin.rstrip("/") for origin in origins]

    @model_validator(mode="after")
    def _deployed_environments_need_config(self) -> Settings:
        if self.environment == Environment.local:
            return self
        missing = [
            name
            for name, value in (("DATABASE_URL", self.database_url), ("CORS_ORIGINS", self.cors_origins))
            if not value
        ]
        if missing:
            raise ValueError(f"{', '.join(missing)} must be set when ENVIRONMENT={self.environment}")
        return self

    @property
    def effective_database_url(self) -> str:
        return self.database_url or LOCAL_DATABASE_URL

    @property
    def allowed_origins(self) -> list[str]:
        if self.cors_origins:
            return self.cors_origins
        return [LOCAL_WEB_ORIGIN]


@lru_cache
def get_settings() -> Settings:
    return Settings()
