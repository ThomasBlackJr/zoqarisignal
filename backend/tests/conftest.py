import io
import wave
import time

import pytest
from fastapi.testclient import TestClient

from app.auth import hasher
from app.config import Settings
from app.db import Base
from app.main import create_app
from app.models import Role, User, Organization, LEGACY_ORG


@pytest.fixture
def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 8000)
    return buffer.getvalue()


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "audio",
        worker_enabled=False,
        max_upload_mb=1,
        transcription_provider="demo",
        qa_provider="demo",
        dev_entitlements_enabled=True,
        mail_delivery="local",
        mail_outbox_dir=tmp_path / "mail",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.db() as db:
        from app.services.rubric import seed_legacy

        db.add(
            Organization(
                id=LEGACY_ORG,
                name="Test workspace",
                subscription_status="active",
                entitlement_source="development",
                entitlement_expires_at=time.time() + 86400,
                onboarding_completed=True,
            )
        )
        db.flush()
        seed_legacy(db)
        db.add(
            User(
                email="admin@example.test",
                name="Test Admin",
                email_verified=True,
                organization_id="00000000-0000-0000-0000-000000000002",
                role=Role.ADMIN,
                password_hash=hasher.hash("test-password-only"),
            )
        )
        db.add(
            User(
                email="supervisor@example.test",
                name="Test Supervisor",
                email_verified=True,
                organization_id="00000000-0000-0000-0000-000000000002",
                role=Role.SUPERVISOR,
                password_hash=hasher.hash("test-password-only"),
            )
        )
        db.commit()
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app, headers={"X-Drive-Request": "1", "Origin": "http://localhost:3000"}) as client:
        yield client


@pytest.fixture
def signed_in(client):
    response = client.post("/auth/login", json={"email": "admin@example.test", "password": "test-password-only"})
    assert response.status_code == 200
    return client
