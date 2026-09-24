import time
from unittest.mock import Mock

from sqlalchemy import select

from app.auth import token_hash
from app.models import Invitation, LEGACY_ORG, User
from .test_customer_entry import mail_token, PASSWORD, register
from .test_supervisor_controls import other_tenant, supervisor

EMAIL = "invited@example.test"


def invite(client, app, email=EMAIL, role="MANAGER"):
    response = client.post("/invitations", json={"email": email, "role": role})
    assert response.status_code == 201, response.text
    assert response.json()["mail_delivery"] == "local"
    return response.json(), mail_token(app, "invite", email)


def login_admin(client):
    assert (
        client.post("/auth/login", json={"email": "admin@example.test", "password": "test-password-only"}).status_code
        == 200
    )


def test_invitation_joins_existing_organization_without_grant_or_employee(signed_in, app):
    invitation, token = invite(signed_in, app)
    assert token not in str(signed_in.get("/team").json())
    with app.state.db() as db:
        stored = db.get(Invitation, invitation["id"])
        assert stored.token_hash == token_hash(token) and stored.token_hash != token
    signed_in.post("/auth/logout")
    preview = signed_in.post("/invitations/preview", json={"token": token})
    assert preview.status_code == 200 and preview.json()["email"] == EMAIL
    response = signed_in.post(
        "/invitations/register", json={"token": token, "email": EMAIL, "name": "New Manager", "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    user = response.json()
    assert user["organization_id"] == LEGACY_ORG and user["role"] == "MANAGER" and user["email_verified"]
    assert signed_in.get("/employees").json()["total"] == 0
    assert signed_in.get("/dashboard").status_code == 200
    assert signed_in.get("/team").status_code == 403
    assert signed_in.post("/organizations", json={"name": "Wrong new organization"}).status_code == 409
    assert signed_in.post("/invitations/accept", json={"token": token}).status_code == 400
    with app.state.db() as db:
        stored = db.get(Invitation, invitation["id"])
        assert stored.status == "accepted" and stored.accepted_by == user["id"] and stored.accepted_at


def test_existing_account_must_authenticate_matching_email_no_password_replacement(signed_in, app):
    invitation, token = invite(signed_in, app)
    assert signed_in.post("/invitations/accept", json={"token": token}).status_code == 403
    assert signed_in.post("/invitations/preview", json={"token": token}).status_code == 200
    registered, _ = register(signed_in, app, EMAIL)
    with app.state.db() as db:
        original_hash = db.get(User, registered["id"]).password_hash
    response = signed_in.post(
        "/invitations/register",
        json={"token": token, "email": EMAIL, "name": "Takeover", "password": "another-passphrase-123"},
    )
    assert response.status_code == 409
    signed_in.post("/auth/logout")
    assert signed_in.post("/invitations/accept", json={"token": token}).status_code == 401
    signed_in.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert signed_in.post("/invitations/accept", json={"token": token}).status_code == 200
    with app.state.db() as db:
        user = db.get(User, registered["id"])
        assert user.password_hash == original_hash and user.organization_id == LEGACY_ORG


def test_invitation_replacement_expiry_revocation_and_scope(signed_in, app):
    first, old_token = invite(signed_in, app)
    second, token = invite(signed_in, app)
    assert signed_in.post("/invitations/preview", json={"token": old_token}).status_code == 400
    with app.state.db() as db:
        db.get(Invitation, second["id"]).expires_at = time.time() - 1
        db.commit()
    assert signed_in.post("/invitations/preview", json={"token": token}).status_code == 400
    third, token = invite(signed_in, app)
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/team").json()["invitations"] == []
    assert signed_in.post("/invitations/" + third["id"] + "/revoke").status_code == 404
    assert signed_in.post("/invitations/accept", json={"token": token}).status_code == 403
    login_admin(signed_in)
    assert signed_in.post("/invitations/" + third["id"] + "/revoke").status_code == 200
    assert signed_in.post("/invitations/preview", json={"token": token}).status_code == 400
    assert signed_in.post("/invitations/preview", json={"token": "A" * 43}).status_code == 400


def test_role_escalation_and_inviter_revocation(signed_in, app):
    assert signed_in.post("/invitations", json={"email": EMAIL, "role": "OWNER"}).status_code == 422
    assert (
        signed_in.post(
            "/invitations", json={"email": EMAIL, "role": "MANAGER", "organization_id": "forged"}
        ).status_code
        == 422
    )
    invitation, token = invite(signed_in, app, role="EMPLOYEE")
    supervisor(signed_in)
    assert signed_in.post("/invitations", json={"email": EMAIL, "role": "ADMIN"}).status_code == 403
    assert signed_in.post("/invitations/" + invitation["id"] + "/revoke").status_code == 403
    with app.state.db() as db:
        inviter = db.scalar(select(User).where(User.email == "admin@example.test"))
        inviter.active = False
        db.commit()
    assert signed_in.post("/invitations/preview", json={"token": token}).status_code == 400


def test_delivery_failure_rolls_back_and_does_not_log_private_payload(signed_in, app, caplog):
    app.state.mail = Mock()
    app.state.mail.send.side_effect = RuntimeError("sensitive-mail-token-or-recipient")
    result = signed_in.post("/invitations", json={"email": EMAIL, "role": "MANAGER"})
    assert result.status_code == 503
    assert "sensitive-mail-token" not in result.text and "sensitive-mail-token" not in caplog.text
    assert signed_in.get("/team").json()["invitations"] == []


def test_invited_employee_cannot_access_operational_data(signed_in, app):
    _, token = invite(signed_in, app, role="EMPLOYEE")
    signed_in.post(
        "/invitations/register", json={"token": token, "email": EMAIL, "name": "Employee", "password": PASSWORD}
    )
    for path in ["/employees", "/dashboard", "/calls", "/batches", "/team"]:
        assert signed_in.get(path).status_code == 403
    assert signed_in.get("/account").status_code == 200
    assert signed_in.post("/invitations", json={"email": "next@example.test", "role": "ADMIN"}).status_code == 403


def test_preferences_persist_per_user_and_reject_forged_modules(signed_in, app):
    default = signed_in.get("/preferences").json()
    assert default["appearance"] == "system" and default["revision"] == 0
    value = {**default, "appearance": "dark", "modules": ["recent", "metrics"]}
    result = signed_in.put("/preferences", json=value)
    assert result.status_code == 200 and result.json()["revision"] == 1
    assert signed_in.put("/preferences", json=value).status_code == 409
    assert signed_in.put("/preferences", json={**result.json(), "user_id": "forged"}).status_code == 422
    assert signed_in.put("/preferences", json={**result.json(), "modules": ["fake_trend"]}).status_code == 422
    assert signed_in.put("/preferences", json={**result.json(), "modules": ["recent", "recent"]}).status_code == 422
    supervisor(signed_in)
    assert signed_in.get("/preferences").json() == default
    assert signed_in.put("/preferences", json={**default, "appearance": "light", "modules": []}).status_code == 200
    login_admin(signed_in)
    assert signed_in.get("/preferences").json() == result.json()
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/preferences").json() == default
    signed_in.post("/auth/logout")
    assert signed_in.get("/preferences").status_code == 401
