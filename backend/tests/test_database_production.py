"""Database safety and migration regression checks; integration uses a disposable schema."""

import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import DatabaseSettings, Settings
from app.db import database_url, make_database


@pytest.mark.parametrize("url", ["sqlite:///./data/drive.db", "sqlite:///:memory:", "sqlite:////tmp/test.db"])
def test_production_rejects_sqlite_without_writing(url, monkeypatch):
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: pytest.fail("configuration wrote to disk"))
    with pytest.raises(ValueError, match="persistent PostgreSQL"):
        DatabaseSettings(_env_file=None, environment="production", database_url=url)


def test_production_requires_explicit_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="persistent PostgreSQL"):
        DatabaseSettings(_env_file=None, environment="production")


@pytest.mark.parametrize(
    "value", ["", "not-a-url", "postgresql:///missing_host", "postgresql://localhost", "mysql://localhost/db"]
)
def test_production_rejects_invalid_database(value):
    with pytest.raises(ValueError, match="DATABASE_URL"):
        DatabaseSettings(_env_file=None, environment="production", database_url=value)


def test_vercel_cannot_default_to_development():
    with pytest.raises(ValueError, match="ENVIRONMENT=production"):
        DatabaseSettings(_env_file=None, environment="development", vercel=True)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_provider_urls_select_installed_driver_without_losing_credentials(scheme):
    value = f"{scheme}://user:p%40ss%2Fword@localhost/signal?sslmode=require"
    settings = DatabaseSettings(_env_file=None, environment="production", database_url=value)
    url = database_url(settings.database_url)
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss/word"
    assert url.query["sslmode"] == "require"
    assert "p%40ss" not in repr(settings)
    engine, _ = make_database(settings.database_url)
    assert engine.dialect.driver == "psycopg"
    engine.dispose()


def test_invalid_database_error_does_not_disclose_input():
    with pytest.raises(ValueError) as error:
        DatabaseSettings(_env_file=None, database_url="invalid-secret-credential")
    assert "invalid-secret-credential" not in str(error.value)


def test_vercel_postgres_does_not_claim_audio_storage_is_ready():
    with pytest.raises(ValueError, match="Vercel recording storage is not implemented"):
        Settings(
            _env_file=None,
            environment="production",
            vercel=True,
            database_url="postgresql://test@localhost/signal_test",
        )


def test_sqlite_persists_locally(tmp_path):
    url = f"sqlite:///{tmp_path / 'nested' / 'test.db'}"
    engine, _ = make_database(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE persisted (value INTEGER)")
        conn.exec_driver_sql("INSERT INTO persisted VALUES (42)")
    engine.dispose()
    engine, _ = make_database(url)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT value FROM persisted").scalar_one() == 42
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    engine.dispose()


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_database(request, tmp_path, monkeypatch):
    admin = None
    schema = "signal_test_" + uuid.uuid4().hex
    if request.param == "postgresql":
        value = os.environ.get("SIGNAL_TEST_POSTGRES_URL")
        if not value:
            pytest.skip("Set SIGNAL_TEST_POSTGRES_URL to a disposable PostgreSQL test database")
        admin, _ = make_database(value)
        with admin.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        url = database_url(value).update_query_dict({"options": f"-csearch_path={schema}"})
        value = url.render_as_string(hide_password=False)
    else:
        value = f"sqlite:///{tmp_path / 'migrations.db'}"
    monkeypatch.setenv("DATABASE_URL", value)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("VERCEL", "0")
    # Migration configuration intentionally does not require application SMTP/audio settings.
    monkeypatch.setenv("MAIL_DELIVERY", "disabled")
    engine, _ = make_database(value)
    try:
        yield engine, value
    finally:
        engine.dispose()
        if admin:
            with admin.begin() as conn:
                conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            admin.dispose()


def test_migrations_preserve_legacy_data_and_auth_contract(migration_database, tmp_path):
    engine, value = migration_database
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    command.upgrade(config, "a2623e115e90")
    metadata = sa.MetaData()
    metadata.reflect(engine)
    with engine.begin() as conn:
        conn.execute(
            metadata.tables["users"]
            .insert()
            .values(
                id="legacy-user",
                email="synthetic@example.test",
                name="Synthetic",
                password_hash="unused",
                role="ADMIN",
                active=True,
            )
        )
        conn.execute(
            metadata.tables["calls"]
            .insert()
            .values(
                id="legacy-call",
                filename="synthetic.wav",
                storage_name="synthetic.wav",
                content_type="audio/wav",
                size_bytes=10,
                created_at=0,
                status="COMPLETED",
                is_demo=True,
                uploaded_by="legacy-user",
            )
        )
        conn.execute(
            metadata.tables["transcripts"]
            .insert()
            .values(
                call_id="legacy-call",
                text="Synthetic preserved transcript",
                segments=[],
                provider="demo",
                model="demo",
                created_at=0,
            )
        )
        conn.execute(
            metadata.tables["qa_evaluations"]
            .insert()
            .values(
                call_id="legacy-call",
                overall_score=50,
                result={"synthetic": True},
                rubric_version="1.0",
                provider="demo",
                model="demo",
                created_at=0,
            )
        )
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # Re-running an applied release is a no-op.
    with engine.begin() as conn:
        assert conn.scalar(sa.text("SELECT text FROM transcripts")) == "Synthetic preserved transcript"
        assert conn.scalar(sa.text("SELECT id FROM qa_evaluations")) == "legacy-call"
        assert conn.scalar(sa.text("SELECT audit_number FROM calls")) == "SIG-00000001"
        assert conn.scalar(sa.text("INSERT INTO audit_sequence DEFAULT VALUES RETURNING id")) == 2
        assert sa.inspect(conn).get_pk_constraint("qa_evaluations")["constrained_columns"] == ["id"]
        assert any(
            c["column_names"] == ["organization_id", "version"]
            for c in sa.inspect(conn).get_unique_constraints("rubrics")
        )
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        database_url=value,
        upload_dir=tmp_path / "test-audio",
        worker_enabled=False,
        transcription_provider="demo",
        qa_provider="demo",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/account").status_code == 401
        assert client.get("/preferences").status_code == 401
