"""Database safety and migration regression checks; integration uses a disposable schema."""

import ast
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from app.config import DatabaseSettings, Settings
from app.db import database_url, make_database


def test_revision_graph_has_unique_ids_and_every_file_reaches_single_head():
    root = Path(__file__).resolve().parents[1]
    revisions = {}
    for path in (root / "migrations" / "versions").glob("*.py"):
        assignments = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"revision", "down_revision"}
        }
        revision = assignments["revision"]
        assert revision not in revisions, (revision, path, revisions.get(revision))
        revisions[revision] = assignments["down_revision"]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["u179570dfe20"]
    assert scripts.get_bases() == ["a2623e115e90"]
    assert {item.revision for item in scripts.walk_revisions()} == set(revisions)
    for revision, parent in revisions.items():
        parents = parent if isinstance(parent, tuple) else (() if parent is None else (parent,))
        assert all(item in revisions for item in parents), revision
        # Every node has a complete ancestor path to the original base.
        assert "a2623e115e90" in {item.revision for item in scripts.walk_revisions(base="base", head=revision)}


@pytest.mark.parametrize("first_branch", ["r846247abd17", "t068469cfd19"])
def test_fresh_upgrade_contains_both_branches_and_lifecycle(migration_database, first_branch):
    from app.db import Base
    from app import models  # noqa: F401

    engine, _ = migration_database
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, first_branch)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)

    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        for table in Base.metadata.sorted_tables:
            assert {column["name"] for column in inspector.get_columns(table.name)} == set(table.columns.keys())
        assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "u179570dfe20"
    # Lifecycle rollback must leave shared ancestor-owned objects intact.
    command.downgrade(config, "6d8f2a91c043")
    inspector = sa.inspect(engine)
    assert "platform_administrators" in inspector.get_table_names()
    assert "created_at" in {c["name"] for c in inspector.get_columns("users")}
    assert "suspended" in {c["name"] for c in inspector.get_columns("organizations")}
    assert "last_login_at" not in {c["name"] for c in inspector.get_columns("users")}
    command.upgrade(config, "head")
    command.check(config)


def test_lifecycle_preserves_shared_account_and_beta_state(migration_database):
    engine, _ = migration_database
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "6d8f2a91c043")
    metadata = sa.MetaData()
    metadata.reflect(engine)
    with engine.begin() as conn:
        organization = conn.scalar(sa.text("SELECT id FROM organizations"))
        conn.execute(metadata.tables["users"].insert().values(
            id="shared-admin", email="shared@example.test", name="Shared", password_hash="unused",
            role="ADMIN", active=True, email_verified=True, created_at=123.0, admin_revision=7,
        ))
        conn.execute(metadata.tables["organizations"].update().values(
            suspended=True, transcription_vocabulary={"terms": ["Synthetic"]},
        ))
        conn.execute(metadata.tables["platform_administrators"].insert().values(user_id="shared-admin", active=True))
        conn.execute(metadata.tables["beta_access"].insert().values(
            organization_id=organization, active=True, expires_at=456.0,
        ))
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as conn:
        assert conn.scalar(sa.text("SELECT created_at FROM users")) == 123.0
        assert conn.scalar(sa.text("SELECT admin_revision FROM users")) == 7
        assert conn.scalar(sa.text("SELECT suspended FROM organizations"))
        assert conn.scalar(sa.text("SELECT user_id FROM platform_administrators")) == "shared-admin"
        assert conn.scalar(sa.text("SELECT expires_at FROM beta_access")) == 456.0
    with pytest.raises(RuntimeError, match="history exists"):
        command.downgrade(config, "6d8f2a91c043")


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
