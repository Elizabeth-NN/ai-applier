from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from pydantic import Field


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "ai_applier"
    db_user: str = "ai_applier_user"
    db_password: str
    clerk_secret_key: str
    gemini_api_key: str | None = None
    gemini_model: str = "gemma-4-26b-a4b-it"
    jobicy_status_sync_enabled: bool = False
    jobicy_status_sync_interval_hours: int = Field(
        default=12,
        ge=1,
        le=168,
    )

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()
