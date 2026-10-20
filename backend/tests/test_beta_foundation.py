import time
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.models import (
    BetaAccess,
    Call,
    LEGACY_ORG,
    Organization,
    PlatformEvent,
    Role,
    User,
)
from app.platform_cli import set_authority
from app.services.entitlements import INACTIVE_ACCESS_MESSAGE, operational_access


def change_role(app, role):
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.role = role
        db.commit()


def platform(app):
    with app.state.db() as db:
        set_authority(db, "admin@example.test", True, "Synthetic test provisioning")


def grant(client, **kwargs):
    return client.put(f"/platform/organizations/{LEGACY_ORG}/beta-access", json={"reason": "Controlled beta", **kwargs})


@pytest.mark.parametrize("role", list(Role))
def test_owner_only_billing(signed_in, app, role):
    change_role(app, role)
    adapter = Mock()
    app.state.billing = adapter
    result = signed_in.get("/billing")
    assert result.status_code == (200 if role == Role.OWNER else 403)
    if role != Role.OWNER:
        assert signed_in.post("/billing/portal").status_code == 403
        assert signed_in.post("/billing/checkout", json={"plan": "starter", "interval": "month"}).status_code == 403
        assert signed_in.get("/account").json()["checkout_available"] is False
    adapter.checkout.assert_not_called()


def test_beta_grant_expiration_revoke_and_independent_subscription(signed_in, app):
    platform(app)
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        org.subscription_status = "inactive"
        db.commit()
    assert signed_in.get("/dashboard").status_code == 403
    assert grant(signed_in).json()["operational_access"]
    assert signed_in.get("/dashboard").status_code == 200
    assert grant(signed_in, expires_at=time.time() - 1).status_code == 422
    assert grant(signed_in, expires_at=time.time() + 3600).status_code == 200
    with app.state.db() as db:
        db.get(BetaAccess, LEGACY_ORG).expires_at = time.time() - 1
        db.commit()
    assert signed_in.get("/dashboard").status_code == 403
    assert grant(signed_in).status_code == 200
    assert (
        signed_in.request(
            "DELETE", f"/platform/organizations/{LEGACY_ORG}/beta-access", json={"reason": "Beta ended"}
        ).json()["operational_access"]
        is False
    )
    # A valid independent entitlement remains usable after beta revocation.
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        org.subscription_status = "active"
        db.commit()
    assert signed_in.get("/dashboard").status_code == 200
    with app.state.db() as db:
        actions = db.scalars(select(PlatformEvent.action)).all()
        assert "beta.grant" in actions and "beta.revoke" in actions


def test_beta_works_in_production_without_stripe(app):
    settings = app.state.settings
    settings.environment = "production"
    settings.stripe_secret_key = settings.stripe_webhook_secret = ""
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        org.beta_access = BetaAccess(active=True)
        db.flush()
        assert operational_access(org, settings)
        org.suspended = True
        assert not operational_access(org, settings)


def test_suspension_existing_session_worker_and_reactivation(signed_in, app, wav_bytes):
    platform(app)
    call_id = signed_in.post("/calls", files={"file": ("fixture.wav", wav_bytes, "audio/wav")}).json()["id"]
    endpoint = f"/platform/organizations/{LEGACY_ORG}/suspension"
    assert signed_in.put(endpoint, json={"suspended": True, "reason": "Pause beta"}).status_code == 200
    assert signed_in.get("/dashboard").json()["detail"] == INACTIVE_ACCESS_MESSAGE
    assert signed_in.get(f"/calls/{call_id}/audio").status_code == 403
    assert signed_in.get("/account").json()["suspended"]
    transcription, qa = Mock(), Mock()
    app.state.processor.transcription, app.state.processor.qa = transcription, qa
    app.state.processor.process(call_id)
    transcription.transcribe.assert_not_called()
    qa.evaluate.assert_not_called()
    with app.state.db() as db:
        assert db.get(Call, call_id).failed_stage == "entitlement"
    assert signed_in.put(endpoint, json={"suspended": False, "reason": "Resume beta"}).json()["operational_access"]
    assert signed_in.get("/dashboard").status_code == 200


@pytest.mark.parametrize("role", list(Role))
def test_customer_roles_never_imply_platform_authority(signed_in, app, role):
    change_role(app, role)
    assert signed_in.get("/platform/organizations").status_code == 403
    assert grant(signed_in).status_code == 403
    assert (
        signed_in.put(
            f"/platform/organizations/{LEGACY_ORG}/suspension", json={"suspended": True, "reason": "Forbidden"}
        ).status_code
        == 403
    )


def test_organization_free_platform_account_and_revocation(signed_in, app):
    platform(app)
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.organization_id, user.role = None, Role.EMPLOYEE
        db.commit()
    assert signed_in.get("/account").status_code == 200
    assert signed_in.get("/dashboard").status_code == 403
    assert signed_in.get("/platform/organizations").status_code == 200
    assert signed_in.post("/platform/organizations", json={"name": "Second beta", "reason": "Pilot"}).status_code == 201
    with app.state.db() as db:
        set_authority(db, "admin@example.test", False, "Revoke platform privileges")
    assert signed_in.get("/platform/organizations").status_code == 403


def test_employee_inactive_message_and_no_operational_access(signed_in, app):
    change_role(app, Role.EMPLOYEE)
    assert signed_in.get("/dashboard").status_code == 403
    with app.state.db() as db:
        db.get(Organization, LEGACY_ORG).suspended = True
        db.commit()
    assert signed_in.get("/account").json()["access_message"] == INACTIVE_ACCESS_MESSAGE
    assert signed_in.get("/calls").json()["detail"] == INACTIVE_ACCESS_MESSAGE


def test_platform_scope_membership_and_audits(signed_in, app):
    platform(app)
    response = signed_in.post("/platform/organizations", json={"name": "Other tenant", "reason": "Pilot"})
    other = response.json()["id"]
    assert signed_in.get(f"/platform/organizations/{other}/members").json()["items"] == []
    details = signed_in.get(f"/platform/organizations/{other}").json()
    assert details["usage"] == {"calls_uploaded": 0, "calls_processed": 0, "qa_evaluations": 0, "reviews_completed": 0}
    assert signed_in.get("/account").json()["organization_id"] == LEGACY_ORG
    # Platform authority does not change tenant resource ownership.
    assert signed_in.get(f"/employees/{other}").status_code == 404
    assert (
        signed_in.post(
            f"/platform/organizations/{other}/invitations/missing/revoke", json={"reason": "Scoped revoke"}
        ).status_code
        == 404
    )
    assert signed_in.get("/platform/activity").json()["items"]


def test_platform_requires_verified_active_account(signed_in, app):
    platform(app)
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.email_verified = False
        db.commit()
    assert signed_in.get("/platform/organizations").status_code == 403
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.active = False
        db.commit()
    assert signed_in.get("/platform/organizations").status_code == 401


def test_platform_owner_invitation_scoped_and_revoked_authority(signed_in, app):
    from .test_customer_entry import mail_token

    platform(app)
    other = signed_in.post("/platform/organizations", json={"name": "Invited org", "reason": "Beta"}).json()["id"]
    path = f"/platform/organizations/{other}/invitations"
    assert (
        signed_in.post(
            path, json={"email": "owner@business.test", "role": "OWNER", "reason": "Initial owner"}
        ).status_code
        == 201
    )
    token = mail_token(app, "invite")
    assert (
        signed_in.post(path, json={"email": "second@example.test", "role": "OWNER", "reason": "Duplicate"}).status_code
        == 409
    )
    assert signed_in.post("/invitations/preview", json={"token": token}).json()["role"] == "OWNER"
    with app.state.db() as db:
        set_authority(db, "admin@example.test", False, "Revoke inviter")
    assert signed_in.post("/invitations/preview", json={"token": token}).status_code == 400
    with app.state.db() as db:
        set_authority(db, "admin@example.test", True, "Restore inviter")
    signed_in.post("/auth/logout")
    response = signed_in.post(
        "/invitations/register",
        json={
            "token": token,
            "email": "owner@business.test",
            "name": "Invited Owner",
            "password": "synthetic-password-only",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "OWNER" and response.json()["organization_id"] == other
    assert signed_in.get("/platform/organizations").status_code == 403
    assert signed_in.get("/dashboard").status_code == 403  # invitation grants no entitlement


def test_suspension_during_transcription_preserves_text_and_blocks_qa(signed_in, app, wav_bytes):
    platform(app)
    cid = signed_in.post("/calls", files={"file": ("fixture.wav", wav_bytes, "audio/wav")}).json()["id"]
    original = app.state.processor.transcription

    class SuspendDuringTranscription:
        name, model = original.name, original.model

        def transcribe(self, path):
            with app.state.db() as db:
                db.get(Organization, LEGACY_ORG).suspended = True
                db.commit()
            return original.transcribe(path)

    app.state.processor.transcription = SuspendDuringTranscription()
    app.state.processor.qa = Mock()
    app.state.processor.process(cid)
    app.state.processor.qa.evaluate.assert_not_called()
    with app.state.db() as db:
        call = db.get(Call, cid)
        assert call.transcript.text and call.failed_stage == "entitlement"


def test_reporting_designation_does_not_grant_authority_and_tenants_stay_isolated(signed_in, app, wav_bytes):
    from .test_supervisor_controls import other_tenant

    cid = signed_in.post("/calls", files={"file": ("fixture.wav", wav_bytes, "audio/wav")}).json()["id"]
    employee = signed_in.post("/employees", json={"name": "Reporting manager", "manager_eligible": True}).json()
    change_role(app, Role.MANAGER)
    assert signed_in.get(f"/employees/{employee['id']}/team").status_code == 200
    assert signed_in.get("/team").status_code == 403
    assert signed_in.delete(f"/calls/{cid}").status_code == 403
    assert signed_in.get("/platform/organizations").status_code == 403
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    for path in (f"/calls/{cid}", f"/calls/{cid}/audio", f"/employees/{employee['id']}/team"):
        assert signed_in.get(path).status_code == 404


def test_beta_migration_preserves_existing_data_and_guards_history(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app.db import make_database

    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "p624025efb15")
    engine, factory = make_database(url)
    try:
        with engine.connect() as conn:
            old = conn.exec_driver_sql("SELECT * FROM rubrics").all()
        command.upgrade(config, "head")
        with factory() as db:
            assert not db.get(Organization, LEGACY_ORG).suspended
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT * FROM rubrics").all() == old
            assert not conn.exec_driver_sql("PRAGMA foreign_key_check").all()
        command.downgrade(config, "p624025efb15")
        command.upgrade(config, "head")
        with factory() as db:
            db.add(BetaAccess(organization_id=LEGACY_ORG, active=True))
            db.commit()
        with pytest.raises(RuntimeError, match="history exists"):
            command.downgrade(config, "p624025efb15")
    finally:
        engine.dispose()
