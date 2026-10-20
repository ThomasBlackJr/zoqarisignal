"""Real organization grants, isolation and worker revocation across merged APIs."""

import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hasher
from app.models import BetaAccess, Call, Invitation, LEGACY_ORG, Organization, User
from tests.test_account_lifecycle import operator, HEADERS
from tests.test_supervisor_controls import other_tenant


def beta_only(app):
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        org.subscription_status = "inactive"
        org.entitlement_source = None
        org.entitlement_expires_at = None
        db.commit()


def grant(admin):
    response = admin.put(f"/platform/organizations/{LEGACY_ORG}/beta-access", json={"reason": "Controlled beta"})
    assert response.status_code == 200


def revoke(admin):
    response = admin.request(
        "DELETE", f"/platform/organizations/{LEGACY_ORG}/beta-access", json={"reason": "Beta withdrawn"}
    )
    assert response.status_code == 200


def test_org_beta_inherited_expired_revoked_and_tenant_isolated(app, signed_in, wav_bytes):
    beta_only(app)
    admin = operator(app)
    other_tenant(app)
    with app.state.db() as db:
        db.add(
            User(
                email="beta-member@example.test",
                name="Member",
                role="REVIEWER",
                organization_id=LEGACY_ORG,
                email_verified=True,
                password_hash=hasher.hash("synthetic-member-passphrase"),
            )
        )
        db.commit()
    member = TestClient(app, headers=HEADERS)
    member.post("/auth/login", json={"email": "beta-member@example.test", "password": "synthetic-member-passphrase"})
    foreign = TestClient(app, headers=HEADERS)
    foreign.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    with app.state.db() as db:
        other = db.scalar(select(User).where(User.email == "other@example.test")).organization
        other.subscription_status = "inactive"
        db.commit()
    for client in (signed_in, member):
        assert client.get("/account").json()["operational_access"] is False
        assert client.get("/dashboard").status_code == 200
    grant(admin)
    for client in (signed_in, member):
        assert client.get("/account").json()["operational_access"]
        assert client.post("/calls", files={"file": ("beta.wav", wav_bytes, "audio/wav")}).status_code == 201
    assert foreign.get("/account").json()["operational_access"] is False
    assert foreign.post("/calls", files={"file": ("foreign.wav", wav_bytes, "audio/wav")}).status_code == 403
    with app.state.db() as db:
        db.get(BetaAccess, LEGACY_ORG).expires_at = time.time() - 1
        db.commit()
    for client in (signed_in, member):
        assert client.get("/account").json()["operational_access"] is False
        assert client.post("/calls/missing/retry").status_code == 403
    grant(admin)
    revoke(admin)
    for client in (signed_in, member):
        assert client.get("/account").status_code == 200
        assert client.get("/account").json()["operational_access"] is False
        assert client.post("/calls/missing/retry").status_code == 403


@pytest.mark.parametrize("during_transcription", [False, True])
def test_beta_revocation_blocks_worker_and_preserves_committed_transcript(
    app, signed_in, wav_bytes, during_transcription
):
    beta_only(app)
    admin = operator(app)
    grant(admin)
    cid = signed_in.post("/calls", files={"file": ("beta.wav", wav_bytes, "audio/wav")}).json()["id"]
    processor = app.state.processor
    original = processor.transcription
    processor.qa = Mock()
    if during_transcription:

        class RevokeDuringTranscription:
            name, model = original.name, original.model

            def transcribe(self, path, *, context=None):
                revoke(admin)
                return original.transcribe(path, context=context)

        processor.transcription = RevokeDuringTranscription()
    else:
        revoke(admin)
        processor.transcription = Mock()
    processor.process(cid)
    processor.qa.evaluate.assert_not_called()
    if not during_transcription:
        processor.transcription.transcribe.assert_not_called()
    with app.state.db() as db:
        call = db.get(Call, cid)
        assert call.failed_stage == "entitlement"
        assert bool(call.transcript) is during_transcription
        if during_transcription:
            assert call.transcript.text


def test_owner_invitation_cannot_create_second_owner_after_issue(app, signed_in):
    from tests.test_customer_entry import mail_token

    admin = operator(app)
    org = admin.post("/platform/organizations", json={"name": "Owner race", "reason": "Test"}).json()["id"]
    result = admin.post(
        f"/platform/organizations/{org}/invitations",
        json={
            "email": "candidate@example.test",
            "role": "OWNER",
            "reason": "Initial owner",
        },
    )
    assert result.status_code == 201
    token = mail_token(app, "invite", "candidate@example.test")
    with app.state.db() as db:
        db.add(
            User(
                email="existing-owner@example.test",
                name="Owner",
                role="OWNER",
                organization_id=org,
                email_verified=True,
                password_hash="unused",
            )
        )
        db.commit()
    response = signed_in.post(
        "/invitations/register",
        json={
            "token": token,
            "email": "candidate@example.test",
            "name": "Candidate",
            "password": "synthetic-passphrase",
        },
    )
    assert response.status_code == 409
    with app.state.db() as db:
        assert db.get(Invitation, result.json()["id"]).status == "pending"
        assert db.scalar(select(User).where(User.email == "candidate@example.test")) is None
