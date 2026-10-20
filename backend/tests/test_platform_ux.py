import pytest
from sqlalchemy import select

from app.models import User, Role, LEGACY_ORG, PlatformEvent
from app.platform_cli import set_authority
from .test_supervisor_controls import other_tenant


def provision(app, client, organization_free=False):
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        if organization_free:
            user.organization_id = None
            user.role = Role.EMPLOYEE
        set_authority(db, user.email, reason="Synthetic platform provisioning")
    assert client.get("/account").status_code == 401
    assert client.post("/auth/login", json={"email": "admin@example.test", "password": "test-password-only"}).status_code == 200


def test_platform_identity_independent_of_membership(signed_in, app):
    assert signed_in.get("/account").json()["is_platform_admin"] is False
    provision(app, signed_in, organization_free=True)
    for path in ("/account", "/auth/me", "/platform/session"):
        data = signed_in.get(path).json()
        assert data["is_platform_admin"] is True
        assert data["organization_id"] is None
        assert data["role"] == "EMPLOYEE"
    assert signed_in.get("/platform/summary").status_code == 200
    assert signed_in.get("/platform/organizations").status_code == 200
    assert signed_in.get("/platform/users").status_code == 200
    assert signed_in.get("/platform/activity").status_code == 200
    assert signed_in.get("/calls").status_code == 403


@pytest.mark.parametrize("role", list(Role))
def test_customer_roles_cannot_access_platform_views(signed_in, app, role):
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.role = role
        db.commit()
    for path in (
        "/platform/session",
        "/platform/summary",
        "/platform/users",
        "/platform/activity",
        f"/platform/organizations/{LEGACY_ORG}/employees",
    ):
        assert signed_in.get(path).status_code == 403


def test_platform_user_filters_cross_organization_and_tenant_access(signed_in, app, wav_bytes):
    call = signed_in.post("/calls", files={"file": ("fixture.wav", wav_bytes, "audio/wav")}).json()["id"]
    other_tenant(app)
    provision(app, signed_in)
    rows = signed_in.get("/platform/users?q=other&role=ADMIN").json()
    assert rows["total"] == 1 and rows["items"][0]["email"] == "other@example.test"
    other_id = rows["items"][0]["organization_id"]
    assert signed_in.get(f"/platform/users?organization_id={other_id}").json()["total"] == 1
    assert signed_in.get(f"/platform/organizations/{other_id}").status_code == 200
    assert signed_in.get(f"/platform/organizations/{other_id}/employees").json()["items"] == []
    assert (
        signed_in.put(
            f"/platform/organizations/{other_id}/beta-access", json={"reason": "Other tenant beta"}
        ).status_code
        == 200
    )
    assert signed_in.get("/account").json()["organization_id"] == LEGACY_ORG
    assert signed_in.get("/platform/users?role=PLATFORM_ADMIN").status_code == 422
    assert signed_in.get("/platform/users?organization_id=missing").status_code == 404
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get(f"/calls/{call}").status_code == 404
    assert signed_in.get("/platform/users").status_code == 403
    with app.state.db() as db:
        assert "users.view" in db.scalars(select(PlatformEvent.action)).all()


def test_provisioning_can_revoke_sessions_without_changing_customer_role(signed_in, app):
    with app.state.db() as db:
        set_authority(db, "admin@example.test", reason="CLI-style grant")
    assert signed_in.get("/account").status_code == 401
    signed_in.post("/auth/login", json={"email": "admin@example.test", "password": "test-password-only"})
    account = signed_in.get("/account").json()
    assert account["is_platform_admin"] and account["role"] == "ADMIN"
    with app.state.db() as db:
        set_authority(db, "admin@example.test", revoke=True, reason="CLI-style revoke")
    assert signed_in.get("/platform/session").status_code == 401
