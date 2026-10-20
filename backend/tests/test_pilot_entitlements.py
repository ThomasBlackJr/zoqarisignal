import argparse
import time
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.config import Settings
from app.db import make_database
from app.models import Call, EntitlementEvent, LEGACY_ORG, Organization, Role, User
from app.pilot_cli import change_pilot, expiry, main
from app.services.entitlements import operational_access
from .test_supervisor_controls import other_tenant


def production(app, client):
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql://fixture@localhost/pilot_test",
        frontend_origin="https://signal.example.test",
        cookie_secure=True,
        mail_delivery="resend",
        resend_api_key="re_synthetic_fixture_only",
        worker_enabled=False,
        upload_dir=app.state.settings.upload_dir,
    )
    # Keep the object captured by middleware/routes, with a validated production policy.
    # The factory/engine remain the disposable SQLite fixture, never this example PG URL.
    app.state.settings.__dict__.update(settings.__dict__)
    app.state.processor.settings = app.state.settings
    app.state.processor.mail = Mock()
    client.base_url = "https://testserver"
    client.headers["Origin"] = settings.frontend_origin
    return settings


def pilot(app, *, revoke=False, expires_at=None):
    with app.state.db() as db:
        change_pilot(
            db,
            LEGACY_ORG,
            "Test workspace",
            "admin@example.test",
            "Approved USPack test pilot",
            revoke=revoke,
            expires_at=expires_at,
        )


def test_production_grant_without_stripe_and_append_only_revoke_audit(app, signed_in):
    settings = production(app, signed_in)
    assert not settings.dev_entitlements_enabled and not settings.stripe_secret_key
    assert signed_in.get("/dashboard").status_code == 200
    assert signed_in.post("/calls/id/retry").status_code == 403
    end = time.time() + 3600
    pilot(app, expires_at=end)
    assert signed_in.get("/calls").status_code == 200
    assert signed_in.get("/account").json()["entitlement_source"] == "pilot"
    pilot(app, revoke=True)
    assert signed_in.get("/dashboard").status_code == 200
    assert signed_in.post("/calls/id/retry").status_code == 403
    assert signed_in.get("/account").status_code == 200
    with app.state.db() as db:
        events = db.scalars(select(EntitlementEvent).order_by(EntitlementEvent.created_at)).all()
        assert [e.action for e in events] == ["pilot_grant", "pilot_revoke"]
        assert all(e.reason == "Approved USPack test pilot" and e.expires_at == end for e in events)
        actor = db.scalar(select(User).where(User.email == "admin@example.test"))
        assert all(e.actor_id == actor.id and e.organization_id == LEGACY_ORG for e in events)
        assert actor.role == Role.ADMIN and actor.email_verified


def test_default_deny_and_no_expiry_are_specific_to_pilot(app, signed_in):
    settings = production(app, signed_in)
    with app.state.db() as db:
        organization = Organization(name="Not approved")
        assert not operational_access(organization, settings)
    pilot(app)
    assert signed_in.get("/dashboard").status_code == 200
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        assert org.entitlement_expires_at is None
        for source in (None, "unknown", "stripe_live", "stripe_test", "development"):
            org.entitlement_source = source
            assert not operational_access(org, settings)
        org.entitlement_source = "pilot"
        org.subscription_status = "trialing"
        assert not operational_access(org, settings)


def test_operator_can_revoke_even_when_the_audited_owner_is_disabled(app):
    pilot(app)
    with app.state.db() as db:
        owner = db.scalar(select(User).where(User.email == "admin@example.test"))
        owner.active, owner.email_verified = False, False
        db.commit()
    # A trusted server operator can reduce access without reactivating a disabled account.
    pilot(app, revoke=True)
    with app.state.db() as db:
        assert db.get(Organization, LEGACY_ORG).subscription_status == "inactive"
        assert len(db.scalars(select(EntitlementEvent)).all()) == 2
    with pytest.raises(ValueError):
        pilot(app)


@pytest.mark.parametrize("expires", [0, -1, float("nan"), float("inf")])
def test_bad_or_elapsed_pilot_expiry_denies(app, signed_in, expires):
    settings = production(app, signed_in)
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        org.entitlement_source = "pilot"
        org.entitlement_expires_at = expires
        assert not operational_access(org, settings)


def test_expiration_denies_api_without_deleting_history(app, signed_in, wav_bytes):
    production(app, signed_in)
    pilot(app, expires_at=time.time() + 3600)
    result = signed_in.post("/calls", files={"file": ("synthetic.wav", wav_bytes, "audio/wav")})
    assert result.status_code == 201
    call_id = result.json()["id"]
    with app.state.db() as db:
        db.get(Organization, LEGACY_ORG).entitlement_expires_at = time.time() - 1
        db.commit()
    for path in ("/dashboard", "/calls", f"/calls/{call_id}", f"/calls/{call_id}/audio", "/team"):
        assert signed_in.get(path).status_code == 200
    assert signed_in.post(f"/calls/{call_id}/retry").status_code == 403
    with app.state.db() as db:
        assert db.get(Call, call_id) is not None


@pytest.mark.parametrize("deny", ["revoked", "expired", "not_granted"])
def test_worker_rechecks_pilot_before_transcription(app, signed_in, wav_bytes, deny):
    production(app, signed_in)
    pilot(app)
    call_id = signed_in.post("/calls", files={"file": ("synthetic.wav", wav_bytes, "audio/wav")}).json()["id"]
    if deny == "revoked":
        pilot(app, revoke=True)
    else:
        with app.state.db() as db:
            org = db.get(Organization, LEGACY_ORG)
            if deny == "expired":
                org.entitlement_expires_at = time.time() - 1
            else:
                org.entitlement_source = None
            db.commit()
    processor = app.state.processor
    processor.transcription.transcribe = Mock()
    processor.qa.evaluate = Mock()
    processor.process(call_id)
    processor.transcription.transcribe.assert_not_called()
    processor.qa.evaluate.assert_not_called()
    with app.state.db() as db:
        assert db.get(Call, call_id).failed_stage == "entitlement"


def test_pilot_worker_completes_and_revocation_between_stages_blocks_qa(app, signed_in, wav_bytes):
    production(app, signed_in)
    pilot(app)
    processor = app.state.processor
    first = signed_in.post("/calls", files={"file": ("first.wav", wav_bytes, "audio/wav")}).json()["id"]
    processor.process(first)
    with app.state.db() as db:
        assert db.get(Call, first).evaluation is not None
    second = signed_in.post("/calls", files={"file": ("second.wav", wav_bytes, "audio/wav")}).json()["id"]
    transcribe = processor.transcription.transcribe

    def revoke_after_audio(path, **options):
        result = transcribe(path, **options)
        pilot(app, revoke=True)
        return result

    processor.transcription.transcribe = Mock(side_effect=revoke_after_audio)
    processor.qa.evaluate = Mock()
    processor.process(second)
    processor.qa.evaluate.assert_not_called()
    with app.state.db() as db:
        call = db.get(Call, second)
        assert call.transcript is not None and call.evaluation is None and call.failed_stage == "entitlement"


def test_pilot_keeps_verification_role_and_organization_isolation(app, signed_in, wav_bytes):
    production(app, signed_in)
    pilot(app)
    call_id = signed_in.post("/calls", files={"file": ("test.wav", wav_bytes, "audio/wav")}).json()["id"]
    other_id, _ = other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/calls").status_code == 200
    assert signed_in.post("/calls/missing/retry").status_code == 403
    with app.state.db() as db:
        with pytest.raises(ValueError, match="Audit actor"):
            change_pilot(db, other_id, "Other organization", "admin@example.test", "Wrong organization actor")
        db.rollback()
        change_pilot(db, other_id, "Other organization", "other@example.test", "Separate approved test organization")
    assert signed_in.get("/calls").json()["total"] == 0
    assert signed_in.get(f"/calls/{call_id}").status_code == 404
    assert signed_in.get(f"/calls/{call_id}/audio").status_code == 404
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "other@example.test"))
        user.role = Role.EMPLOYEE
        db.commit()
    assert signed_in.get("/calls").status_code == 403
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "other@example.test"))
        user.role, user.email_verified = Role.ADMIN, False
        db.commit()
    assert signed_in.get("/calls").status_code == 403


@pytest.mark.parametrize(
    "change", ["wrong_name", "wrong_actor", "employee", "unverified", "inactive", "stripe", "reason", "expired"]
)
def test_trusted_operator_rejects_unsafe_grants_atomically(app, change):
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        if change == "employee":
            user.role = Role.EMPLOYEE
        if change == "unverified":
            user.email_verified = False
        if change == "inactive":
            user.active = False
        if change == "stripe":
            db.get(Organization, LEGACY_ORG).entitlement_source = "stripe_live"
        db.commit()
        with pytest.raises(ValueError):
            change_pilot(
                db,
                LEGACY_ORG,
                "Wrong" if change == "wrong_name" else "Test workspace",
                "missing@example.test" if change == "wrong_actor" else "admin@example.test",
                " " if change == "reason" else "Explicit test approval",
                expires_at=time.time() - 1 if change == "expired" else None,
            )
        db.rollback()
        assert db.scalar(select(EntitlementEvent)) is None
        assert db.get(Organization, LEGACY_ORG).entitlement_source != "pilot"


def test_no_public_pilot_activation_or_privileged_registration(signed_in):
    assert signed_in.post("/subscription/pilot-activation").status_code == 404
    assert signed_in.post("/organizations", json={"name": "USPack", "entitlement_source": "pilot"}).status_code == 422


def test_cli_configuration_failure_does_not_expose_credentials(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "invalid-secret-database-credential")
    with pytest.raises(SystemExit) as error:
        main(
            [
                "grant",
                "--organization-id",
                LEGACY_ORG,
                "--confirm-name",
                "Test workspace",
                "--actor-email",
                "admin@example.test",
                "--reason",
                "Configuration check",
            ]
        )
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert "invalid-secret" not in captured.err + captured.out
    assert "configuration privately" in captured.err


@pytest.mark.parametrize("value", ["2026-01-01T00:00:00Z", "2099-01-01", "bad", "nan"])
def test_cli_rejects_bad_expiry(value):
    with pytest.raises(argparse.ArgumentTypeError):
        expiry(value)


def test_cli_grants_and_revokes_without_app_import_or_email(app, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", app.state.settings.database_url)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("VERCEL", "0")
    args = [
        "--organization-id",
        LEGACY_ORG,
        "--confirm-name",
        "Test workspace",
        "--actor-email",
        "admin@example.test",
        "--reason",
        "CLI test approval",
    ]
    main(["grant", *args, "--expires-at", "2099-01-01T00:00:00Z"])
    main(["revoke", *args])
    assert "revoked" in capsys.readouterr().out
    with app.state.db() as db:
        assert db.get(Organization, LEGACY_ORG).subscription_status == "inactive"
        assert len(db.scalars(select(EntitlementEvent)).all()) == 2


def test_audit_migration_preserves_existing_events_and_guards_downgrade(tmp_path, monkeypatch):
    value = f"sqlite:///{tmp_path / 'pilot-migration.db'}"
    monkeypatch.setenv("DATABASE_URL", value)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("VERCEL", "0")
    config = Config("alembic.ini")
    command.upgrade(config, "s957358bec18")
    engine, factory = make_database(value)
    try:
        # Seed the historical schema without today's additional User columns.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id,email,name,password_hash,organization_id,email_verified,role,active) VALUES ('old-user','legacy@example.test','Legacy','unused',:org,1,'ADMIN',1)"
                ),
                {"org": LEGACY_ORG},
            )
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO entitlement_events (id, organization_id, actor_id, action, created_at, expires_at) VALUES (:id,:org,:actor,:action,1,100)"
                ),
                {"id": "old-event", "org": LEGACY_ORG, "actor": "old-user", "action": "development_activated"},
            )
        command.upgrade(config, "head")
        command.check(config)
        with factory() as db:
            old = db.get(EntitlementEvent, "old-event")
            assert old.expires_at == 100 and old.reason is None
            org = db.get(Organization, LEGACY_ORG)
            change_pilot(db, org.id, org.name, "legacy@example.test", "Explicit migration test", expires_at=None)
        with pytest.raises(RuntimeError, match="history exists"):
            command.downgrade(config, "s957358bec18")
    finally:
        engine.dispose()
