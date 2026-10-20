import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hasher
from app.models import AccountEvent, Invitation, PlatformAdministrator, Role, User, VerificationCode, Call
from app.platform_cli import set_authority
from tests.test_customer_entry import register, PASSWORD, mail_token
from tests.test_supervisor_controls import other_tenant

HEADERS = {"X-Drive-Request": "1", "Origin": "http://localhost:3000"}
OPERATOR = "operator@zoqari.test"


def operator(app):
    with app.state.db() as db:
        user = User(
            email=OPERATOR,
            name="Zoqari Operator",
            password_hash=hasher.hash(PASSWORD),
            role=Role.EMPLOYEE,
            email_verified=True,
        )
        db.add(user)
        db.commit()
        set_authority(db, OPERATOR, reason="Synthetic operator bootstrap")
    client = TestClient(app, headers=HEADERS)
    assert client.post("/auth/login", json={"email": OPERATOR, "password": PASSWORD}).status_code == 200
    return client


def new_owner(client, app):
    user, code = register(client, app, "owner@uspack.test")
    assert client.post("/auth/verify-email", json={"code": code}).status_code == 200
    org = client.post("/organizations", json={"name": "USPack"})
    assert org.status_code == 201
    return user, org.json()["organization_id"]


def test_complete_new_owner_pending_platform_approval_and_revoke(client, app, wav_bytes):
    user, org_id = new_owner(client, app)
    assert client.get("/dashboard").status_code == 200
    assert client.post("/calls/missing/retry").status_code == 403
    admin = operator(app)
    # Platform authority is separate; it does not impersonate a customer or grant workspace review.
    assert admin.get("/calls").status_code == 403
    result = admin.post(
        f"/platform/organizations/{org_id}/pilot", json={"reason": "USPack approved", "expires_at": time.time() + 3600}
    )
    assert result.status_code == 200
    assert client.get("/dashboard").status_code == 200
    call_id = client.post("/calls", files={"file": ("synthetic.wav", wav_bytes, "audio/wav")}).json()["id"]
    app.state.processor.process(call_id)
    assert client.get(f"/calls/{call_id}").json()["status"] == "completed"
    assert (
        admin.post(f"/platform/organizations/{org_id}/pilot/revoke", json={"reason": "Pilot ended"}).status_code == 200
    )
    assert client.get("/dashboard").status_code == 200
    assert client.post("/calls/missing/retry").status_code == 403
    org = admin.get(f"/platform/organizations/{org_id}").json()
    assert [e["action"] for e in org["pilot_history"]] == ["pilot_revoke", "pilot_grant"]
    assert all(e["actor"] == "Zoqari Operator" for e in org["pilot_history"])
    detail = admin.get(f"/platform/users/{user['id']}").json()
    assert detail["created_at"] and detail["last_login_at"]
    assert {e["action"] for e in detail["events"]} >= {"account_registered", "email_verified", "session_started"}
    assert "password_hash" not in detail and "code_hash" not in detail


@pytest.mark.parametrize(
    "path,body",
    [
        ("/platform/users", None),
        ("/platform/organizations", None),
        ("/platform/session", None),
        ("/platform/users/unknown/status", {"active": True, "reason": "Forged"}),
        ("/platform/users/unknown/verification", {"reason": "Forged"}),
        ("/platform/organizations/unknown/pilot", {"reason": "Forged"}),
        ("/platform/organizations/unknown/suspension", {"suspended": False, "reason": "Forged"}),
    ],
)
def test_tenant_admin_cannot_use_platform_routes(signed_in, path, body):
    result = signed_in.get(path) if body is None else signed_in.post(path, json=body)
    assert result.status_code == 403


def test_platform_revocation_and_unverified_authority_fail_closed(app):
    admin = operator(app)
    with app.state.db() as db:
        target = db.scalar(select(User).where(User.email == OPERATOR))
        target.email_verified = False
        db.commit()
    assert admin.get("/platform/users").status_code == 403
    with app.state.db() as db:
        target = db.scalar(select(User).where(User.email == OPERATOR))
        target.email_verified = True
        db.get(PlatformAdministrator, target.id).active = False
        db.commit()
    assert admin.get("/platform/users").status_code == 403


def test_admin_verification_reuses_template_and_preserves_pending_challenge(client, app, monkeypatch):
    monkeypatch.setattr("app.services.verification.secrets.randbelow", Mock(side_effect=[111111, 222222]))
    registration = client.post(
        "/auth/register", json={"name": "Pending", "email": "pending@uspack.test", "password": PASSWORD}
    )
    challenge = registration.json()["challenge"]
    with app.state.db() as db:
        target = db.scalar(select(User).where(User.email == "pending@uspack.test"))
        target_id = target.id
        db.get(VerificationCode, target_id).sent_at -= 61
        db.commit()
    admin = operator(app)
    result = admin.post(f"/platform/users/{target_id}/verification", json={"reason": "Recipient requested resend"})
    assert result.status_code == 200 and set(result.json()) == {"message"}
    assert "222222" not in result.text and challenge not in result.text
    assert client.post("/auth/verify-email", json={"challenge": challenge, "code": "111111"}).status_code == 400
    assert client.post("/auth/verify-email", json={"challenge": challenge, "code": "222222"}).status_code == 200
    assert (
        admin.post(f"/platform/users/{target_id}/verification", json={"reason": "Already verified"}).status_code == 409
    )


def test_admin_mail_failure_is_sanitized_and_audited(app):
    admin = operator(app)
    with app.state.db() as db:
        target = User(name="Pending", email="pending@uspack.test", password_hash=hasher.hash(PASSWORD))
        db.add(target)
        db.commit()
        target_id = target.id
    app.state.mail = Mock()
    app.state.mail.send.side_effect = RuntimeError("sensitive-provider-credential")
    for suffix in ("verification", "password-reset"):
        result = admin.post(f"/platform/users/{target_id}/{suffix}", json={"reason": "User requested help"})
        assert result.status_code == 503 and "sensitive-provider" not in result.text
    with app.state.db() as db:
        events = db.scalars(select(AccountEvent).where(AccountEvent.user_id == target_id)).all()
        assert {e.action for e in events} == {"verification_request_failed", "password_reset_request_failed"}
        assert all(e.reason == "User requested help" for e in events)
        assert db.get(VerificationCode, target_id) is None


def test_account_deactivation_revokes_sessions_and_requires_valid_password_to_disclose_status(app):
    admin = operator(app)
    with app.state.db() as db:
        target = User(
            name="Member", email="member@uspack.test", password_hash=hasher.hash(PASSWORD), email_verified=True
        )
        db.add(target)
        db.commit()
        target_id = target.id
    member = TestClient(app, headers=HEADERS)
    assert member.post("/auth/login", json={"email": "member@uspack.test", "password": PASSWORD}).status_code == 200
    assert (
        admin.post(
            f"/platform/users/{target_id}/status", json={"active": False, "reason": "Pilot member withdrawn"}
        ).status_code
        == 200
    )
    assert member.get("/account").status_code == 401
    assert member.post("/auth/login", json={"email": "member@uspack.test", "password": "wrong"}).status_code == 401
    result = member.post("/auth/login", json={"email": "member@uspack.test", "password": PASSWORD})
    assert result.status_code == 403 and "inactive" in result.json()["detail"]
    assert (
        admin.post(
            f"/platform/users/{target_id}/status", json={"active": True, "reason": "Access restored"}
        ).status_code
        == 200
    )
    assert member.get("/account").status_code == 401
    assert member.post("/auth/login", json={"email": "member@uspack.test", "password": PASSWORD}).status_code == 200
    events = admin.get(f"/platform/users/{target_id}").json()["events"]
    assert {e["action"] for e in events} >= {"account_activated", "account_deactivated"}


def test_verified_account_discovers_and_accepts_only_its_own_pending_invitation(app, signed_in):
    email = "invited@uspack.test"
    invite = signed_in.post("/invitations", json={"email": email, "role": "REVIEWER"})
    invite_id = invite.json()["id"]
    # Another logged-in identity cannot consume it, even knowing its non-secret ID.
    assert signed_in.post(f"/invitations/{invite_id}/accept").status_code == 400
    member = TestClient(app, headers=HEADERS)
    body = {"name": "Invited", "email": email, "password": PASSWORD}
    response = member.post("/auth/register", json=body)
    assert member.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    assert member.get("/account").json()["pending_invitations"] == []
    assert member.post(f"/invitations/{invite_id}/accept").status_code == 403
    code = mail_token(app, email=email)
    assert (
        member.post("/auth/verify-email", json={"challenge": response.json()["challenge"], "code": code}).status_code
        == 200
    )
    account = member.get("/account").json()
    assert len(account["pending_invitations"]) == 1 and not account["organization_id"]
    assert "token" not in account["pending_invitations"][0]
    assert member.post(f"/invitations/{invite_id}/accept").status_code == 200
    assert member.get("/account").json()["organization_id"] == signed_in.get("/account").json()["organization_id"]
    assert member.get("/dashboard").status_code == 200
    assert member.post(f"/invitations/{invite_id}/accept").status_code == 400
    assert member.post("/organizations", json={"name": "Duplicate"}).status_code == 409


def test_expired_pending_invitation_cannot_be_accepted_by_id(app, signed_in):
    response = signed_in.post("/invitations", json={"email": "member@uspack.test", "role": "EMPLOYEE"})
    invite_id = response.json()["id"]
    with app.state.db() as db:
        db.get(Invitation, invite_id).expires_at = time.time() - 1
        member = User(
            name="Member", email="member@uspack.test", password_hash=hasher.hash(PASSWORD), email_verified=True
        )
        db.add(member)
        db.commit()
    signed_in.post("/auth/login", json={"email": "member@uspack.test", "password": PASSWORD})
    assert signed_in.post(f"/invitations/{invite_id}/accept").status_code == 400
    assert signed_in.get("/account").json()["pending_invitations"] == []


def test_repeat_signup_does_not_replace_password_or_reveal_account_state(client, app, monkeypatch):
    generator = Mock(side_effect=[111111, 222222])
    monkeypatch.setattr("app.services.verification.secrets.randbelow", generator)
    body = {"name": "Member", "email": "repeat@uspack.test", "password": PASSWORD}
    first = client.post("/auth/register", json=body)
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == body["email"]))
        old_hash = user.password_hash
        db.get(VerificationCode, user.id).sent_at -= 61
        db.commit()
    retry = client.post("/auth/register", json={**body, "password": "a-different-passphrase-123"})
    assert retry.status_code == first.status_code == 201 and retry.json()["message"] == first.json()["message"]
    with app.state.db() as db:
        assert db.scalar(select(User).where(User.email == body["email"])).password_hash == old_hash
    assert (
        client.post("/auth/verify-email", json={"challenge": retry.json()["challenge"], "code": "222222"}).status_code
        == 200
    )
    app.state.mail = Mock()
    result = client.post("/auth/register", json=body)
    assert result.status_code == 201 and result.json()["message"] == first.json()["message"]
    app.state.mail.send.assert_not_called()


def test_suspension_blocks_worker_and_only_owner_requires_pause_before_deactivation(client, app, wav_bytes):
    owner, org_id = new_owner(client, app)
    admin = operator(app)
    admin.post(f"/platform/organizations/{org_id}/pilot", json={"reason": "Approved"})
    call_id = client.post("/calls", files={"file": ("test.wav", wav_bytes, "audio/wav")}).json()["id"]
    assert (
        admin.post(
            f"/platform/users/{owner['id']}/status", json={"active": False, "reason": "Protect ownership"}
        ).status_code
        == 409
    )
    assert (
        admin.post(
            f"/platform/organizations/{org_id}/suspension", json={"suspended": True, "reason": "Incident pause"}
        ).status_code
        == 200
    )
    assert client.get("/account").json()["organization_suspended"]
    assert client.get("/calls").status_code == 403
    processor = app.state.processor
    processor.transcription.transcribe = Mock()
    processor.qa.evaluate = Mock()
    processor.process(call_id)
    processor.transcription.transcribe.assert_not_called()
    processor.qa.evaluate.assert_not_called()
    with app.state.db() as db:
        assert db.get(Call, call_id).failed_stage == "entitlement"
    assert (
        admin.post(
            f"/platform/users/{owner['id']}/status", json={"active": False, "reason": "Suspended owner"}
        ).status_code
        == 200
    )


def test_privileged_mutations_require_reason_and_reject_role_actor_or_email_forgery(app, client):
    user, org_id = new_owner(client, app)
    admin = operator(app)
    for body in ({"reason": "ok", "actor_id": user["id"]}, {"reason": "ok", "role": "OWNER"}):
        assert admin.post(f"/platform/organizations/{org_id}/pilot", json=body).status_code == 422
    assert (
        admin.post(
            f"/platform/users/{user['id']}/status", json={"active": True, "reason": "ok", "email": "attacker@bad.test"}
        ).status_code
        == 422
    )
    assert admin.post(f"/platform/users/{user['id']}/email", json={"email": "attacker@bad.test"}).status_code == 404
    assert (
        admin.post(
            f"/platform/users/{admin.get('/auth/me').json()['id']}/status",
            json={"active": False, "reason": "Self lockout"},
        ).status_code
        == 409
    )


def test_platform_initiated_password_reset_keeps_existing_session_until_redeemed(app, client):
    owner, _ = new_owner(client, app)
    admin = operator(app)
    result = admin.post(f"/platform/users/{owner['id']}/password-reset", json={"reason": "Owner requested recovery"})
    assert result.status_code == 200 and set(result.json()) == {"message"}
    assert client.get("/account").status_code == 200
    token = mail_token(app, "reset", "owner@uspack.test")
    assert token not in result.text
    assert (
        client.post("/auth/reset-password", json={"token": token, "password": "replacement-passphrase-123"}).status_code
        == 200
    )
    assert client.get("/account").status_code == 401


def test_platform_authority_does_not_change_tenant_scoped_customer_api(app, signed_in, wav_bytes):
    call_id = signed_in.post("/calls", files={"file": ("test.wav", wav_bytes, "audio/wav")}).json()["id"]
    other_tenant(app)
    with app.state.db() as db:
        set_authority(db, "other@example.test", reason="Separate tenant operator")
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/platform/organizations").status_code == 200
    assert signed_in.get(f"/calls/{call_id}").status_code == 404
    assert signed_in.get(f"/calls/{call_id}/audio").status_code == 404


def test_repeat_registration_only_authenticates_with_existing_password(client, app):
    body = {"name": "Member", "email": "repeat-login@uspack.test", "password": PASSWORD}
    first = client.post("/auth/register", json=body)
    code = mail_token(app, email=body["email"])
    assert client.post("/auth/verify-email", json={"challenge": first.json()["challenge"], "code": code}).status_code == 200
    stranger = TestClient(app, headers=HEADERS)
    wrong = stranger.post("/auth/register", json={**body, "password": "different-password-123"})
    assert wrong.status_code == 201 and not wrong.json().get("signed_in")
    assert stranger.get("/account").status_code == 401
    correct = stranger.post("/auth/register", json=body)
    assert correct.status_code == 201 and correct.json()["signed_in"]
    assert stranger.get("/account").json()["email_verified"]


def test_trusted_bootstrap_requires_verified_account_preserves_role_and_revokes_sessions(app):
    admin = operator(app)
    with app.state.db() as db:
        target = db.scalar(select(User).where(User.email == OPERATOR))
        assert target.role == Role.EMPLOYEE and target.organization_id is None
        set_authority(db, OPERATOR, revoke=True, reason="Operator authority removed")
        assert target.role == Role.EMPLOYEE and target.organization_id is None
        target.email_verified = False
        db.commit()
        with pytest.raises(ValueError, match="verified"):
            set_authority(db, OPERATOR, reason="Unverified grant forbidden")
        with pytest.raises(ValueError, match="verified"):
            set_authority(db, "missing@zoqari.test", reason="No implicit user creation")
        actions = db.scalars(select(AccountEvent.action).where(AccountEvent.user_id == target.id)).all()
        assert "platform_granted" in actions and "platform_revoked" in actions
    assert admin.get("/platform/session").status_code == 401
