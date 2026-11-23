from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url
from pydantic import Field


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "ai_applier"
    db_user: str = "ai_applier_user"
    db_password: str | None = None
    database_url_env: str | None = Field(
        default=None,
        validation_alias="DATABASE_URL",
    )
    clerk_secret_key: str
    frontend_origins: str = "http://localhost:3000"
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
        validate_by_name=True,
    )

    @property
    def allowed_frontend_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.frontend_origins.split(",")
            if origin.strip()
        ]

    @property
    def database_url(self) -> URL:
        if self.database_url_env:
            connection_string = self.database_url_env.strip()

            # Some hosting providers still supply the legacy postgres:// scheme.
            if connection_string.startswith("postgres://"):
                connection_string = "postgresql://" + connection_string[
                    len("postgres://"):
                ]

            parsed_url = make_url(connection_string)

            if parsed_url.get_backend_name() != "postgresql":
                raise ValueError("DATABASE_URL must use PostgreSQL.")

            return parsed_url.set(drivername="postgresql+psycopg")

        if not self.db_password:
            raise ValueError(
                "Set DATABASE_URL or DB_PASSWORD."
            )

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()
