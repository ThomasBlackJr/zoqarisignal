import pytest
from sqlalchemy import select, func

from app.auth import hasher
from app.models import (
    User,
    LEGACY_ORG,
    Session,
    Employee,
    PlatformEvent,
    Call,
    Evaluation,
    ScoreAdjustment,
    CoachingDraft,
)
from app.platform_cli import set_authority
from .test_supervisor_controls import other_tenant, complete


@pytest.fixture
def admin(signed_in, app):
    with app.state.db() as db:
        set_authority(db, "admin@example.test", reason="Synthetic administration")
    assert signed_in.post("/auth/login", json={"email": "admin@example.test", "password": "test-password-only"}).status_code == 200
    return signed_in


def target(app):
    with app.state.db() as db:
        return db.scalar(select(User.id).where(User.email == "supervisor@example.test"))


def body(client, uid, **values):
    return {
        "confirmed": True,
        "reason": "Synthetic admin test",
        "revision": client.get(f"/platform/users/{uid}").json()["revision"],
        **values,
    }


def token(app, purpose, email):
    # Private credentials consumed internally by tests only; never output them.
    paths = sorted(app.state.settings.mail_outbox_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for p in paths:
        text = p.read_text(encoding="utf-8")
        if f"To: {email}\n" in text and f"Purpose: {purpose}\n" in text:
            return next(line.split("#token=", 1)[1] for line in text.splitlines() if "#token=" in line)
    raise AssertionError("Expected private test mail")


def test_profile_status_and_no_credentials(admin, app):
    uid = target(app)
    r = admin.put(f"/platform/users/{uid}/profile", json=body(admin, uid, first_name="Updated", last_name="Person"))
    assert r.status_code == 200 and r.json()["name"] == "Updated Person"
    assert r.json()["updated_at"] and r.json()["created_at"]
    stale = {"confirmed": True, "reason": "stale", "revision": 0, "first_name": "Stale", "last_name": "Name"}
    assert admin.put(f"/platform/users/{uid}/profile", json=stale).status_code == 409
    assert admin.put(f"/platform/users/{uid}/status", json=body(admin, uid, active=False)).status_code == 200
    assert admin.get("/platform/users?status=disabled").json()["total"] == 1
    assert admin.put(f"/platform/users/{uid}/status", json=body(admin, uid, active=True)).json()["active"]
    response = admin.get(f"/platform/users/{uid}")
    assert "password_hash" not in response.text and "token_hash" not in response.text
    with app.state.db() as db:
        assert db.get(User, uid).password_hash not in response.text
    for v in (False, "true"):
        assert (
            admin.put(f"/platform/users/{uid}/status", json=body(admin, uid, active=False, confirmed=v)).status_code
            == 422
        )
    assert (
        admin.put(
            f"/platform/users/{uid}/profile", json=body(admin, uid, first_name="Bad", password="not-accepted")
        ).status_code
        == 422
    )


def test_membership_roles_and_employee_relationships(admin, app):
    uid = target(app)
    employee = admin.post("/employees", json={"name": "Linked employee"}).json()
    manager = admin.post("/employees", json={"name": "Team manager", "manager_eligible": True}).json()
    assert (
        admin.put(f"/platform/users/{uid}/employee-link", json=body(admin, uid, employee_id=employee["id"])).status_code
        == 200
    )
    d = admin.get(f"/platform/users/{uid}").json()
    assert (
        admin.put(
            f"/platform/users/{uid}/manager",
            json=body(admin, uid, manager_id=manager["id"], employee_revision=d["employee"]["revision"]),
        ).json()["employee"]["manager_name"]
        == "Team manager"
    )
    assert (
        admin.put(
            f"/platform/users/{uid}/membership", json=body(admin, uid, organization_id=LEGACY_ORG, role="MANAGER")
        ).json()["role"]
        == "MANAGER"
    )
    other_tenant(app)
    with app.state.db() as db:
        org = db.scalar(select(User.organization_id).where(User.email == "other@example.test"))
        foreign = Employee(name="Foreign manager", organization_id=org, manager_eligible=True)
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    d = admin.get(f"/platform/users/{uid}").json()
    assert (
        admin.put(
            f"/platform/users/{uid}/manager",
            json=body(admin, uid, manager_id=foreign_id, employee_revision=d["employee"]["revision"]),
        ).status_code
        == 404
    )
    assert (
        admin.put(f"/platform/users/{uid}/employee-link", json=body(admin, uid, employee_id=foreign_id)).status_code
        == 404
    )
    r = admin.put(f"/platform/users/{uid}/membership", json=body(admin, uid, organization_id=org, role="REVIEWER"))
    assert r.status_code == 200 and r.json()["employee"] is None
    assert r.json()["organization_id"] == org
    with app.state.db() as db:
        assert db.get(Employee, employee["id"]).linked_user_id is None
    assert (
        admin.put(f"/platform/users/{uid}/membership", json=body(admin, uid, organization_id=None)).json()[
            "organization_id"
        ]
        is None
    )


def test_owner_transfer_explicit_and_never_ownerless(admin, app):
    uid = target(app)
    with app.state.db() as db:
        old = db.get(User, uid)
        old.role = "OWNER"
        replacement = User(
            name="New Owner",
            email="replacement@example.test",
            organization_id=LEGACY_ORG,
            role="EMPLOYEE",
            email_verified=True,
            password_hash=hasher.hash("synthetic-only-passphrase"),
        )
        db.add(replacement)
        db.commit()
        new_id = replacement.id
    for path, fields in (
        ("status", {"active": False}),
        ("membership", {"organization_id": None}),
        ("email", {"email": "changed@example.test"}),
    ):
        assert admin.put(f"/platform/users/{uid}/{path}", json=body(admin, uid, **fields)).status_code == 409
    transfer = {"current_owner_id": uid, "new_owner_id": new_id, "reason": "Owner replacement"}
    path = f"/platform/organizations/{LEGACY_ORG}/owner"
    assert admin.put(path, json=transfer).status_code == 422
    assert admin.put(path, json={**transfer, "confirmed": False}).status_code == 422
    assert admin.put(path, json={**transfer, "confirmed": True, "current_owner_id": "wrong"}).status_code == 409
    other_tenant(app)
    with app.state.db() as db:
        foreign_id = db.scalar(select(User.id).where(User.email == "other@example.test"))
    assert admin.put(path, json={**transfer, "confirmed": True, "new_owner_id": foreign_id}).status_code == 409
    with app.state.db() as db:
        db.get(User, new_id).email_verified = False
        db.commit()
    assert admin.put(path, json={**transfer, "confirmed": True}).status_code == 409
    with app.state.db() as db:
        db.get(User, new_id).email_verified = True
        db.commit()
    assert admin.put(path, json={**transfer, "confirmed": True}).status_code == 200
    with app.state.db() as db:
        assert db.get(User, uid).role == "ADMIN" and db.get(User, new_id).role == "OWNER"
        history = db.scalar(select(PlatformEvent).where(PlatformEvent.action == "owner.changed"))
        assert history.details == {"old_owner_id": uid, "new_owner_id": new_id}
        assert (
            db.scalar(
                select(func.count()).select_from(User).where(User.role == "OWNER", User.organization_id == LEGACY_ORG)
            )
            == 1
        )
    assert admin.put(f"/platform/users/{new_id}/status", json=body(admin, new_id, active=False)).status_code == 409
    assert admin.put(f"/platform/users/{uid}/status", json=body(admin, uid, active=False)).status_code == 200


def test_reset_verification_and_email_change_revoke_credentials(admin, app):
    uid = target(app)
    old_email = "supervisor@example.test"
    assert admin.post(f"/platform/users/{uid}/password-reset", json=body(admin, uid)).status_code == 200
    reset = token(app, "reset", old_email)
    with app.state.db() as db:
        db.add(Session(token_hash="synthetic-old-session", user_id=uid, expires_at=9999999999))
        db.commit()
    r = admin.put(f"/platform/users/{uid}/email", json=body(admin, uid, email=" NEW@example.test "))
    assert r.status_code == 200 and r.json()["email"] == "new@example.test"
    assert r.json()["email_verified"] is False
    assert (
        admin.post("/auth/reset-password", json={"token": reset, "password": "another-synthetic-password"}).status_code
        == 400
    )
    with app.state.db() as db:
        assert not db.scalar(select(Session).where(Session.user_id == uid))
    from .test_customer_entry import mail_token
    verify = mail_token(app, "verify", "new@example.test")
    with app.state.db() as db:
        from app.models import VerificationCode
        db.get(VerificationCode, uid).sent_at -= 61
        db.commit()
    assert admin.post(f"/platform/users/{uid}/verification", json=body(admin, uid)).status_code == 200
    # Resending replaces the old code; only the authenticated recipient redeems it.
    from fastapi.testclient import TestClient
    recipient = TestClient(app, headers={"X-Drive-Request": "1", "Origin": "http://localhost:3000"})
    assert recipient.post("/auth/login", json={"email": "new@example.test", "password": "test-password-only"}).status_code == 200
    assert recipient.post("/auth/verify-email", json={"code": verify}).status_code == 400
    verify = mail_token(app, "verify", "new@example.test")
    assert recipient.post("/auth/verify-email", json={"code": verify}).status_code == 200
    with app.state.db() as db:
        assert db.get(User, uid).email_verified


def test_deactivation_and_membership_removal_preserve_history(admin, app, wav_bytes):
    admin.post("/auth/login", json={"email": "supervisor@example.test", "password": "test-password-only"})
    call = complete(admin, app, wav_bytes)
    admin.post("/auth/login", json={"email": "admin@example.test", "password": "test-password-only"})
    uid = target(app)
    with app.state.db() as db:
        evaluation = db.scalar(select(Evaluation.id).where(Evaluation.call_id == call["id"]))
        original = db.get(Call, call["id"]).transcript.text
        qa = db.get(Evaluation, evaluation)
        qa.reviewed_by, qa.reviewed_at = uid, 1.0
        adjustment = ScoreAdjustment(
            evaluation_id=evaluation,
            category_key="synthetic",
            score=1,
            previous_score=0,
            reason="Retained audit",
            changed_by=uid,
        )
        db.add(adjustment)
        db.add(
            CoachingDraft(
                organization_id=LEGACY_ORG,
                issue_id="retention-test",
                fingerprint="synthetic",
                choice={"note": "Retained coaching"},
                provider="demo",
                model="demo",
            )
        )
        db.add(
            PlatformEvent(actor_id=uid, organization_id=LEGACY_ORG, action="synthetic.retention", reason="Retain actor")
        )
        db.commit()
        adjustment_id = adjustment.id
    assert admin.put(f"/platform/users/{uid}/status", json=body(admin, uid, active=False)).status_code == 200
    assert (
        admin.put(f"/platform/users/{uid}/membership", json=body(admin, uid, organization_id=None)).status_code == 200
    )
    with app.state.db() as db:
        assert db.get(Call, call["id"]).transcript.text == original
        assert db.get(Evaluation, evaluation) is not None
        assert db.get(Evaluation, evaluation).reviewed_by == uid
        assert db.get(ScoreAdjustment, adjustment_id).changed_by == uid
        assert db.get(CoachingDraft, (LEGACY_ORG, "retention-test")) is not None
        assert db.scalar(select(PlatformEvent).where(PlatformEvent.action == "synthetic.retention")).actor_id == uid
        assert db.get(User, uid) is not None


def test_platform_account_protection_and_mail_rollback(admin, app):
    me = admin.get("/account").json()["id"]
    assert admin.put(f"/platform/users/{me}/status", json=body(admin, me, active=False)).status_code == 409
    assert (
        admin.put(f"/platform/users/{me}/email", json=body(admin, me, email="other-admin@example.test")).status_code
        == 409
    )
    uid = target(app)

    class FailingMail:
        def send(self, *args):
            raise RuntimeError("private-provider-payload")

    app.state.mail = FailingMail()
    r = admin.put(f"/platform/users/{uid}/email", json=body(admin, uid, email="failed@example.test"))
    assert r.status_code == 503 and "private-provider-payload" not in r.text
    with app.state.db() as db:
        assert db.get(User, uid).email == "supervisor@example.test"


def test_create_account_sends_setup_without_exposing_passwords(admin, app):
    r = admin.post(
        "/platform/users",
        json={
            "first_name": "Created",
            "last_name": "Person",
            "email": "created@example.test",
            "reason": "Setup",
            "confirmed": True,
        },
    )
    assert r.status_code == 201 and r.json()["organization_id"] is None and not r.json()["email_verified"]
    assert "password_hash" not in r.text and "token_hash" not in r.text
    from .test_customer_entry import mail_token
    assert mail_token(app, "verify", "created@example.test") and token(app, "reset", "created@example.test")
    assert admin.get("/platform/users?status=unverified").json()["total"] == 1


@pytest.mark.parametrize("role", ["OWNER", "ADMIN"])
def test_customers_cannot_manage_platform_accounts(signed_in, app, role):
    uid = target(app)
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.role = role
        db.commit()
    for path in (f"/platform/users/{uid}", f"/platform/organizations/{LEGACY_ORG}/ownership"):
        assert signed_in.get(path).status_code == 403
    for path, values in (
        ("profile", {"first_name": "Bad"}),
        ("status", {"active": False}),
        ("membership", {"organization_id": None}),
    ):
        assert (
            signed_in.put(
                f"/platform/users/{uid}/{path}", json={"confirmed": True, "reason": "forged", "revision": 0, **values}
            ).status_code
            == 403
        )


def test_account_metadata_migration_preserves_existing_values(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app.db import make_database

    url = f"sqlite:///{tmp_path / 'metadata.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "q735136fac16")
    engine, _ = make_database(url)
    try:
        with engine.begin() as db:
            db.exec_driver_sql(
                "INSERT INTO users(id,email,name,password_hash,role,active,email_verified) VALUES('legacy','legacy@example.test','Legacy Name','unchanged','EMPLOYEE',1,1)"
            )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as db:
            assert tuple(
                db.exec_driver_sql(
                    "SELECT name,password_hash,created_at,last_session_at,admin_revision FROM users"
                ).one()
            ) == ("Legacy Name", "unchanged", None, None, 0)
            assert not db.exec_driver_sql("PRAGMA foreign_key_check").all()
        command.downgrade(config, "q735136fac16")
        command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_replacement_owner_invitation_is_confirmed_candidate_not_transfer(admin, app):
    uid = target(app)
    with app.state.db() as db:
        db.get(User, uid).role = "OWNER"
        db.commit()
    payload = {
        "email": "candidate@example.test",
        "role": "ADMIN",
        "purpose": "owner_replacement",
        "reason": "Replacement candidate",
    }
    path = f"/platform/organizations/{LEGACY_ORG}/invitations"
    assert admin.post(path, json=payload).status_code == 422
    response = admin.post(path, json={**payload, "confirmed": True})
    assert response.status_code == 201
    invitation = token(app, "invite", "candidate@example.test")
    joined = admin.post(
        "/invitations/register",
        json={
            "token": invitation,
            "email": "candidate@example.test",
            "name": "Candidate",
            "password": "synthetic-candidate-passphrase",
        },
    )
    assert joined.status_code == 201 and joined.json()["role"] == "ADMIN"
    with app.state.db() as db:
        assert db.get(User, uid).role == "OWNER"
        assert db.scalar(select(PlatformEvent).where(PlatformEvent.action == "user.created")) is not None
