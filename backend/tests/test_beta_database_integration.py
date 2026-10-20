"""Application beta controls on migrated SQLite and real disposable PostgreSQL."""

from unittest.mock import Mock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.auth import hasher
from app.config import Settings
from app.main import create_app
from app.models import Call, LEGACY_ORG, Organization, User
from app.platform_cli import set_authority
from tests import test_database_production as database_tests

migration_database = database_tests.migration_database


def test_migrated_database_platform_grant_members_and_worker_revoke(migration_database, tmp_path, wav_bytes):
    engine, url = migration_database
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(
        _env_file=None,
        database_url=url,
        upload_dir=tmp_path / "audio",
        worker_enabled=False,
        transcription_provider="demo",
        qa_provider="demo",
        mail_delivery="local",
        mail_outbox_dir=tmp_path / "mail",
    )
    app = create_app(settings)
    password = "synthetic-integration-password"
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        org.subscription_status = "inactive"
        for email, role, organization_id in (
            ("owner@example.test", "OWNER", LEGACY_ORG),
            ("member@example.test", "REVIEWER", LEGACY_ORG),
            ("platform@example.test", "EMPLOYEE", None),
        ):
            db.add(
                User(
                    email=email,
                    name=email.split("@")[0],
                    role=role,
                    organization_id=organization_id,
                    password_hash=hasher.hash(password),
                    email_verified=True,
                )
            )
        db.commit()
        set_authority(db, "platform@example.test", reason="Disposable integration bootstrap")
    headers = {"X-Drive-Request": "1", "Origin": "http://localhost:3000"}
    try:
        with (
            TestClient(app, headers=headers) as platform,
            TestClient(app, headers=headers) as owner,
            TestClient(app, headers=headers) as member,
        ):
            for client, email in (
                (platform, "platform@example.test"),
                (owner, "owner@example.test"),
                (member, "member@example.test"),
            ):
                assert client.post("/auth/login", json={"email": email, "password": password}).status_code == 200
            assert platform.get("/platform/summary").status_code == 200
            assert owner.get("/platform/summary").status_code == 403
            assert not owner.get("/account").json()["operational_access"]
            endpoint = f"/platform/organizations/{LEGACY_ORG}/beta-access"
            assert platform.put(endpoint, json={"reason": "Approved integration beta"}).status_code == 200
            assert owner.get("/account").json()["operational_access"]
            assert member.get("/account").json()["operational_access"]
            upload = member.post("/calls", files={"file": ("synthetic.wav", wav_bytes, "audio/wav")})
            assert upload.status_code == 201
            cid = upload.json()["id"]
            assert platform.request("DELETE", endpoint, json={"reason": "Revoked before provider"}).status_code == 200
            app.state.processor.transcription = Mock()
            app.state.processor.qa = Mock()
            app.state.processor.process(cid)
            app.state.processor.transcription.transcribe.assert_not_called()
            app.state.processor.qa.evaluate.assert_not_called()
            with app.state.db() as db:
                assert db.get(Call, cid).failed_stage == "entitlement"
            for client in (owner, member):
                assert client.get("/account").status_code == 200
                assert not client.get("/account").json()["operational_access"]
                assert client.post(f"/calls/{cid}/retry").status_code == 403
            command.check(Config("alembic.ini"))
    finally:
        app.state.engine.dispose()
        engine.dispose()
