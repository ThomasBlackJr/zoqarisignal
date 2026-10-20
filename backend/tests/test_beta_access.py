import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AccountEvent, EntitlementEvent, LEGACY_ORG, Organization, Role, User
from tests.test_account_lifecycle import operator, HEADERS
from tests.test_customer_entry import PASSWORD, mail_token
from tests.test_pilot_entitlements import production


def test_no_beta_account_dashboard_and_scoped_reads_remain_available(app, signed_in, wav_bytes):
    production(app, signed_in)
    assert signed_in.get("/dashboard").status_code == 200
    assert signed_in.get("/briefing").status_code == 200
    assert signed_in.get("/config").status_code == 200
    assert signed_in.get("/calls").json()["total"] == 0
    assert not signed_in.get("/account").json()["operational_access"]
    assert signed_in.post("/calls", files={"file": ("blocked.wav", wav_bytes, "audio/wav")}).status_code == 403


@pytest.mark.parametrize(
    "path,body",
    [
        ("/calls/unknown/retry", None),
        ("/calls/unknown/reevaluate", {}),
        ("/batches", {}),
        ("/batches/unknown/items/unknown/upload", None),
        ("/briefing/issues/unknown/generate", {"fingerprint": "a" * 64}),
    ],
)
def test_no_beta_cannot_directly_initiate_any_analysis_api(app, signed_in, path, body):
    production(app, signed_in)
    response = signed_in.post(path, json=body) if body is not None else signed_in.post(path)
    assert response.status_code == 403
    assert "Beta access required" in response.text


def test_optional_beta_reason_is_audited_and_inherits_for_future_members(app, signed_in, wav_bytes):
    admin = operator(app)
    result = admin.post(f"/platform/organizations/{LEGACY_ORG}/pilot", json={})
    assert result.status_code == 200
    invitation = signed_in.post("/invitations", json={"email": "future@uspack.test", "role": "REVIEWER"})
    assert invitation.status_code == 201
    member = TestClient(app, headers=HEADERS)
    joined = member.post(
        "/invitations/register",
        json={
            "token": mail_token(app, "invite", "future@uspack.test"),
            "email": "future@uspack.test",
            "name": "Future Member",
            "password": PASSWORD,
        },
    )
    assert joined.status_code == 201
    assert member.get("/account").json()["operational_access"]
    call = member.post("/calls", files={"file": ("allowed.wav", wav_bytes, "audio/wav")})
    assert call.status_code == 201
    with app.state.db() as db:
        events = db.scalars(select(EntitlementEvent).where(EntitlementEvent.action == "pilot_grant")).all()
        assert len(events) == 1 and events[0].reason and events[0].actor_id
        assert db.scalar(select(AccountEvent).where(AccountEvent.action == "pilot_granted"))
    assert admin.post(f"/platform/organizations/{LEGACY_ORG}/pilot/revoke", json={}).status_code == 200
    for client in [signed_in, member]:
        assert client.get("/dashboard").status_code == 200
        assert client.get("/calls").status_code == 200
        assert client.post("/calls", files={"file": ("denied.wav", wav_bytes, "audio/wav")}).status_code == 403
    processor = app.state.processor
    processor.transcription.transcribe = Mock()
    processor.qa.evaluate = Mock()
    processor.process(call.json()["id"])
    processor.transcription.transcribe.assert_not_called()
    processor.qa.evaluate.assert_not_called()


def test_membership_removal_loses_access_without_invalidating_login(app, signed_in, wav_bytes):
    operator_client = operator(app)
    operator_client.post(f"/platform/organizations/{LEGACY_ORG}/pilot", json={})
    call_id = signed_in.post("/calls", files={"file": ("before.wav", wav_bytes, "audio/wav")}).json()["id"]
    with app.state.db() as db:
        member = db.scalar(select(User).where(User.email == "admin@example.test"))
        member.organization_id = None  # Trusted test fixture; no new membership-management API.
        db.commit()
    assert signed_in.get("/account").json()["organization_id"] is None
    assert not signed_in.get("/account").json()["operational_access"]
    assert signed_in.get("/dashboard").json()["total"] == 0
    assert signed_in.get("/briefing").json()["recent"] == []
    assert signed_in.get(f"/calls/{call_id}").status_code == 403
    assert signed_in.post("/calls", files={"file": ("after.wav", wav_bytes, "audio/wav")}).status_code == 403
    assert (
        signed_in.post(
            "/auth/login", json={"email": "admin@example.test", "password": "test-password-only"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.REVIEWER, Role.MANAGER, Role.ADMIN])
def test_beta_never_bypasses_roles_and_unverified_never_enters_workspace(app, signed_in, wav_bytes, role):
    operator(app).post(f"/platform/organizations/{LEGACY_ORG}/pilot", json={})
    with app.state.db() as db:
        db.scalar(select(User).where(User.email == "admin@example.test")).role = role
        db.commit()
    assert signed_in.get("/dashboard").status_code == 200
    assert signed_in.get("/account").json()["operational_access"]
    result = signed_in.post("/calls", files={"file": ("role.wav", wav_bytes, "audio/wav")})
    assert result.status_code == (403 if role == Role.EMPLOYEE else 201)
    with app.state.db() as db:
        db.scalar(select(User).where(User.email == "admin@example.test")).email_verified = False
        db.commit()
    assert signed_in.get("/dashboard").status_code == 403


def test_expiration_retains_login_dashboard_but_denies_product(app, signed_in, wav_bytes):
    admin = operator(app)
    admin.post(f"/platform/organizations/{LEGACY_ORG}/pilot", json={"expires_at": time.time() + 60})
    with app.state.db() as db:
        db.get(Organization, LEGACY_ORG).entitlement_expires_at = time.time() - 1
        db.commit()
    assert signed_in.get("/dashboard").status_code == 200
    assert signed_in.get("/briefing").status_code == 200
    assert signed_in.post("/calls", files={"file": ("expired.wav", wav_bytes, "audio/wav")}).status_code == 403
    assert admin.get(f"/platform/organizations/{LEGACY_ORG}").json()["signal_access"] == "NO ACCESS"
    assert (
        signed_in.post(
            "/auth/login", json={"email": "admin@example.test", "password": "test-password-only"}
        ).status_code
        == 200
    )
