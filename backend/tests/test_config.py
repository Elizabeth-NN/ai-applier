import pytest
from sqlalchemy.engine import URL

from app.core.config import Settings


def make_settings(**overrides):
    values = {
        "db_password": "local-test-password",
        "clerk_secret_key": "test-clerk-secret",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_database_url_uses_existing_local_database_settings():
    settings = make_settings(
        db_host="localhost",
        db_port=5432,
        db_name="ai_applier",
        db_user="ai_applier_user",
    )

    url = settings.database_url

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "localhost"
    assert url.port == 5432
    assert url.database == "ai_applier"
    assert url.username == "ai_applier_user"


def test_database_url_accepts_render_postgresql_connection_string():
    settings = make_settings(
        database_url_env=(
            "postgresql://production_user:production-password"
            "@production-host:5432/production_db"
        )
    )

    url = settings.database_url

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "production-host"
    assert url.database == "production_db"
    assert url.username == "production_user"


def test_database_url_accepts_legacy_postgres_scheme():
    settings = make_settings(
        database_url_env=(
            "postgres://production_user:production-password"
            "@production-host:5432/production_db"
        )
    )

    assert settings.database_url.drivername == "postgresql+psycopg"


def test_database_url_preserves_query_parameters():
    settings = make_settings(
        database_url_env=(
            "postgresql://user:password@host:5432/db"
            "?sslmode=require"
        )
    )

    assert settings.database_url.query["sslmode"] == "require"


def test_database_url_rejects_non_postgresql_scheme():
    settings = make_settings(database_url_env="sqlite:///test.db")

    with pytest.raises(ValueError, match="must use PostgreSQL"):
        _ = settings.database_url


def test_database_url_requires_password_or_connection_string():
    settings = make_settings(db_password=None)

    with pytest.raises(ValueError, match="DATABASE_URL or DB_PASSWORD"):
        _ = settings.database_url
