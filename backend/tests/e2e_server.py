"""Isolated browser-test backend. Never seeds the normal development database."""

import os
import tempfile
import time
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from app.auth import hasher
from app.config import Settings
from app.main import create_app
from app.models import Role, User, Organization, LEGACY_ORG


if __name__ == "__main__":
    folder = Path(tempfile.mkdtemp(prefix="drive-e2e-"))
    os.environ["DATABASE_URL"] = f"sqlite:///{folder / 'drive.db'}"
    os.environ["UPLOAD_DIR"] = str(folder / "audio")
    os.environ["TRANSCRIPTION_PROVIDER"] = "demo"
    os.environ["QA_PROVIDER"] = "demo"
    os.environ["FRONTEND_ORIGIN"] = "http://localhost:3001"
    os.environ["WORKER_ENABLED"] = "true"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEV_ENTITLEMENTS_ENABLED"] = "true"
    os.environ["MAIL_DELIVERY"] = "local"
    os.environ["MAIL_OUTBOX_DIR"] = os.environ["DRIVE_E2E_MAIL_FOLDER"]
    command.upgrade(Config("alembic.ini"), "head")
    app = create_app(Settings(_env_file=None))
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        org.subscription_status = "active"
        org.entitlement_source = "development"
        org.entitlement_expires_at = time.time() + 86400
        db.add(
            User(
                email="reviewer@example.test",
                name="Jordan Morgan",
                email_verified=True,
                organization_id="00000000-0000-0000-0000-000000000002",
                role=Role.ADMIN,
                password_hash=hasher.hash(os.environ["DRIVE_TEST_PASSWORD"]),
            )
        )
        db.commit()
    uvicorn.run(app, host="127.0.0.1", port=8001)
