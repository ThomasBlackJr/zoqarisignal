import time
import re
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.auth import token_hash, verify
from app.config import Settings
from app.models import (
    VerificationCode,
    AccountToken,
    Call,
    EntitlementEvent,
    LEGACY_ORG,
    Organization,
    Role,
    Session,
    User,
)
from app.services.entitlements import operational_access

PASSWORD = "customer-passphrase-123"
EMAIL = "owner@business.test"


def mail_token(app, purpose="verify", email=EMAIL):
    messages = sorted(app.state.settings.mail_outbox_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime_ns)
    for path in reversed(messages):
        content = path.read_text(encoding="utf-8")
        if f"To: {email}\n" in content and f"Purpose: {'verify_code' if purpose == 'verify' else purpose}\n" in content:
            if purpose == "verify":
                return re.search(r"Verification code: ([0-9]{6})", content).group(1)
            link = next(line for line in content.splitlines() if line.startswith("http"))
            return parse_qs(urlparse(link).fragment)["token"][0]
    raise AssertionError("Expected a private local mail message")


def register(client, app, email=EMAIL):
    response = client.post("/auth/register", json={"name": "Business Owner", "email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    client.verification_challenge = response.json()["challenge"]
    login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json(), mail_token(app, email=email)


def organization(client, app, email=EMAIL):
    user, token = register(client, app, email)
    assert client.post("/auth/verify-email", json={"code": token}).status_code == 200
    created = client.post("/organizations", json={"name": "Customer business"})
    assert created.status_code == 201
    return created.json()


def grant(db, org_id=LEGACY_ORG, status="active"):
    org = db.get(Organization, org_id)
    org.subscription_status = status
    org.entitlement_source = "development"
    org.entitlement_expires_at = time.time() + 86400
    db.commit()


def test_registration_verification_owner_and_subscription_gate(client, app, wav_bytes):
    user, token = register(client, app)
    assert user["organization_id"] is None and user["email_verified"] is False
    assert "password" not in str(user) and token not in str(user)
    assert "HttpOnly" in client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).headers["set-cookie"]
    assert client.get("/auth/me").status_code == 200
    assert client.post("/organizations", json={"name": "Business"}).status_code == 403
    with app.state.db() as db:
        stored = db.get(VerificationCode, user["id"])
        assert stored and stored.code_hash != token and verify(token, stored.code_hash)
        assert verify(PASSWORD, db.get(User, user["id"]).password_hash)
    assert client.post("/auth/verify-email", json={"code": token}).status_code == 200
    assert client.post("/auth/verify-email", json={"code": token}).status_code == 400
    assert client.post("/organizations", json={"name": "Company", "organization_id": LEGACY_ORG}).status_code == 422
    created = client.post("/organizations", json={"name": "  Company  "}).json()
    assert created["role"] == "OWNER" and created["organization_id"] != LEGACY_ORG
    assert client.post("/organizations", json={"name": "Second"}).status_code == 409
    for path in ("/config", "/calls", "/dashboard", "/rubrics", "/onboarding"):
        assert client.get(path).status_code == 403
    assert client.post("/calls", files={"file": ("sample.wav", wav_bytes, "audio/wav")}).status_code == 403
    assert client.get("/account").json()["subscription_status"] == "inactive"
    assert client.post("/subscription/development-activation").status_code == 200
    assert client.get("/dashboard").json()["total"] == 0
    rubrics = client.get("/rubrics").json()
    assert len(rubrics) == 1 and sum(c["weight"] for c in rubrics[0]["categories"]) == 100
    assert client.get("/account").json()["checkout_available"] is False
    assert (
        client.post(
            "/users",
            json={"name": "Other owner", "email": "other@business.test", "password": PASSWORD, "role": "OWNER"},
        ).status_code
        == 403
    )
    with app.state.db() as db:
        events = db.scalars(select(EntitlementEvent)).all()
        assert len(events) == 1 and events[0].actor_id == user["id"]


@pytest.mark.parametrize(
    "change",
    [
        {"email": "not-an-email"},
        {"email": "x@domain"},
        {"email": "x\n@y.test"},
        {"name": "  "},
        {"password": "short"},
        {"password": "aaaaaaaaaaaa"},
        {"password": "password1234"},
        {"role": "ADMIN"},
        {"organization_id": LEGACY_ORG},
    ],
)
def test_registration_rejects_invalid_or_privileged_fields(client, change):
    response = client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": PASSWORD, **change})
    assert response.status_code == 422
    assert PASSWORD not in response.text


def test_duplicate_normalized_email_and_resend_invalidates_old_link(client, app):
    _, old = register(client, app)
    duplicate = client.post(
        "/auth/register", json={"name": "Other", "email": " OWNER@BUSINESS.TEST ", "password": PASSWORD}
    )
    assert duplicate.status_code == 201 and "challenge" in duplicate.json()
    assert client.post("/auth/verification").status_code == 429
    with app.state.db() as db:
        db.scalar(select(VerificationCode)).sent_at = time.time() - 61
        db.commit()
    assert client.post("/auth/verification").status_code == 200
    new = mail_token(app)
    assert new != old
    assert client.post("/auth/verify-email", json={"code": old}).status_code == 400
    assert client.post("/auth/verify-email", json={"code": new}).status_code == 200


def test_expired_and_wrong_purpose_tokens_do_not_verify(client, app):
    user, token = register(client, app)
    assert (
        client.post("/auth/reset-password", json={"token": token, "password": "new-passphrase-123"}).status_code == 422
    )
    with app.state.db() as db:
        db.get(VerificationCode, user["id"]).expires_at = time.time() - 1
        db.commit()
    assert client.post("/auth/verify-email", json={"code": token}).status_code == 400


def test_password_reset_single_use_replaces_links_and_revokes_all_sessions(client, app):
    user, _ = register(client, app)
    with app.state.db() as db:
        db.add(Session(token_hash=token_hash("other-session"), user_id=user["id"], expires_at=time.time() + 1000))
        db.commit()
    response = client.post("/auth/forgot-password", json={"email": EMAIL})
    assert response.status_code == 200
    old = mail_token(app, "reset")
    assert old not in response.text
    client.post("/auth/forgot-password", json={"email": EMAIL})
    new = mail_token(app, "reset")
    assert client.post("/auth/reset-password", json={"token": old, "password": "new-passphrase-123"}).status_code == 400
    assert client.post("/auth/reset-password", json={"token": new, "password": "new-passphrase-123"}).status_code == 200
    assert client.get("/auth/me").status_code == 401
    with app.state.db() as db:
        assert db.scalars(select(Session).where(Session.user_id == user["id"])).all() == []
    assert client.post("/auth/reset-password", json={"token": new, "password": "new-passphrase-123"}).status_code == 400
    assert client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": EMAIL, "password": "new-passphrase-123"}).status_code == 200


def test_mail_failure_does_not_claim_delivery_leak_or_create_account(client, app, caplog):
    private = "sensitive-mail-credential"
    app.state.mail.send = Mock(side_effect=RuntimeError(private))
    with caplog.at_level("INFO", logger="drive"):
        response = client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": PASSWORD})
    assert response.status_code == 503
    assert private not in caplog.text and EMAIL not in caplog.text and PASSWORD not in caplog.text
    with app.state.db() as db:
        assert db.scalar(select(User).where(User.email == EMAIL)) is None
    known = client.post("/auth/forgot-password", json={"email": "admin@example.test"})
    unknown = client.post("/auth/forgot-password", json={"email": "missing@business.test"})
    assert known.json() == unknown.json() and known.status_code == 200


@pytest.mark.parametrize("status", ["inactive", "past_due", "canceled", "unknown"])
def test_subscription_states_block_all_operations_but_keep_account(signed_in, app, status):
    with app.state.db() as db:
        grant(db, status=status)
    assert signed_in.get("/account").status_code == 200
    assert signed_in.get("/dashboard").status_code == 403
    assert signed_in.post("/calls/id/retry").status_code == 403
    assert signed_in.get("/calls/id/audio").status_code == 403
    assert signed_in.get("/calls/id/evaluations").status_code == 403
    assert signed_in.post("/rubrics", json={"name": "New", "categories": []}).status_code == 403


@pytest.mark.parametrize("mode", ["expired", "unknown_source", "disabled", "trialing"])
def test_entitlement_requires_known_enabled_unexpired_source(signed_in, app, mode):
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        if mode == "expired":
            org.entitlement_expires_at = time.time() - 1
        elif mode == "unknown_source":
            org.entitlement_source = "pretend-payment"
        elif mode == "disabled":
            app.state.settings.dev_entitlements_enabled = False
        else:
            org.subscription_status = "trialing"
        db.commit()
    assert signed_in.get("/calls").status_code == (200 if mode == "trialing" else 403)


@pytest.mark.parametrize("role", [Role.MANAGER, Role.REVIEWER, Role.SUPERVISOR, Role.EMPLOYEE])
def test_roles_cannot_manage_ownership_scorecards_or_entitlement(signed_in, app, role):
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.role = role
        db.commit()
    assert signed_in.post("/subscription/development-activation").status_code == 403
    assert signed_in.post("/rubrics", json={"name": "New", "categories": []}).status_code == 403
    assert signed_in.get("/dashboard").status_code == (403 if role == Role.EMPLOYEE else 200)


@pytest.mark.parametrize(
    "settings",
    [
        {"environment": "production", "dev_entitlements_enabled": True},
        {"environment": "production", "mail_delivery": "local"},
        {"frontend_origin": "https://public.example.test", "dev_entitlements_enabled": True},
        {"frontend_origin": "https://public.example.test", "mail_delivery": "local"},
    ],
)
def test_development_features_cannot_run_in_production(settings):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **settings)


def test_production_configuration_and_disabled_activation(signed_in, app):
    settings = Settings(
        _env_file=None,
        environment="production",
        cookie_secure=True,
        frontend_origin="https://signal.example.test",
        mail_delivery="smtp",
        smtp_host="smtp.example.test",
        mail_from="signal@example.test",
    )
    with app.state.db() as db:
        assert not operational_access(db.get(Organization, LEGACY_ORG), settings)
    app.state.settings.dev_entitlements_enabled = False
    assert signed_in.post("/subscription/development-activation").status_code == 404


def test_worker_denies_before_transcription(signed_in, app, wav_bytes):
    call_id = signed_in.post("/calls", files={"file": ("test.wav", wav_bytes, "audio/wav")}).json()["id"]
    with app.state.db() as db:
        grant(db, status="canceled")
    processor = app.state.processor
    processor.transcription.transcribe = Mock()
    processor.qa.evaluate = Mock()
    processor.process(call_id)
    processor.transcription.transcribe.assert_not_called()
    processor.qa.evaluate.assert_not_called()
    with app.state.db() as db:
        call = db.get(Call, call_id)
        assert call.failed_stage == "entitlement" and call.transcript is None


def test_access_expires_after_transcription_retry_uses_saved_transcript(signed_in, app, wav_bytes):
    call_id = signed_in.post("/calls", files={"file": ("test.wav", wav_bytes, "audio/wav")}).json()["id"]
    processor = app.state.processor
    original = processor.transcription.transcribe

    def transcribe(path):
        result = original(path)
        with app.state.db() as db:
            grant(db, status="past_due")
        return result

    processor.transcription.transcribe = Mock(side_effect=transcribe)
    original_qa = processor.qa.evaluate
    processor.qa.evaluate = Mock(wraps=original_qa)
    processor.process(call_id)
    processor.qa.evaluate.assert_not_called()
    with app.state.db() as db:
        call = db.get(Call, call_id)
        saved = call.transcript.text
        assert call.failed_stage == "entitlement"
        grant(db)
    assert signed_in.post(f"/calls/{call_id}/retry").status_code == 200
    processor.process(call_id)
    assert processor.transcription.transcribe.call_count == 1
    assert processor.qa.evaluate.call_count == 1
    detail = signed_in.get(f"/calls/{call_id}").json()
    assert detail["status"] == "completed" and detail["transcript"]["text"] == saved


def test_onboarding_and_activation_are_tenant_scoped(client, app, wav_bytes):
    user = organization(client, app)
    own = user["organization_id"]
    # A guessed ID in a body cannot change the server-selected tenant.
    assert client.post("/subscription/development-activation", json={"organization_id": LEGACY_ORG}).status_code == 200
    with app.state.db() as db:
        assert db.get(Organization, LEGACY_ORG).onboarding_completed
        assert not db.get(Organization, own).onboarding_completed
        assert db.scalars(select(EntitlementEvent).where(EntitlementEvent.organization_id == LEGACY_ORG)).all() == []
    assert client.get("/onboarding").json() == {"completed": False, "has_interactions": False}
    assert client.post("/onboarding/complete", json={"skip": False}).status_code == 409
    assert client.post("/calls", files={"file": ("own.wav", wav_bytes, "audio/wav")}).status_code == 201
    assert client.post("/onboarding/complete", json={"skip": False}).status_code == 200
    other = organization(client, app, "other@company.test")
    assert other["organization_id"] != own
    assert client.get("/account").json()["operational_access"] is False
    assert client.post("/subscription/development-activation").status_code == 200
    assert client.get("/onboarding").json() == {"completed": False, "has_interactions": False}
    assert client.get("/dashboard").json()["total"] == 0
    assert client.post("/onboarding/complete", json={"skip": True}).status_code == 200


def test_account_request_limiter_and_csrf(client, app):
    assert client.post("/auth/register", json={}, headers={"Origin": "https://evil.test"}).status_code == 403
    assert (
        client.post("/auth/forgot-password", json={"email": EMAIL}, headers={"X-Drive-Request": ""}).status_code == 403
    )
    for _ in range(20):
        assert client.post("/auth/forgot-password", json={"email": EMAIL}).status_code == 200
    assert client.post("/auth/forgot-password", json={"email": EMAIL}).status_code == 429


def test_disabled_delivery_is_honest_and_does_not_create_account(client, app):
    app.state.settings.mail_delivery = "disabled"
    assert client.get("/auth/options").json()["registration_available"] is False
    assert (
        client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": PASSWORD}).status_code == 503
    )
    assert client.post("/auth/forgot-password", json={"email": EMAIL}).status_code == 503


def test_expired_reset_token_cannot_change_password(client, app):
    user, _ = register(client, app)
    client.post("/auth/forgot-password", json={"email": EMAIL})
    token = mail_token(app, "reset")
    with app.state.db() as db:
        db.get(AccountToken, token_hash(token)).expires_at = time.time() - 1
        db.commit()
    assert (
        client.post("/auth/reset-password", json={"token": token, "password": "new-passphrase-123"}).status_code == 400
    )
    with app.state.db() as db:
        assert verify(PASSWORD, db.get(User, user["id"]).password_hash)


def test_concurrent_verification_consumes_token_once(client, app):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient

    _, token = register(client, app)

    def redeem():
        with TestClient(app, headers={"X-Drive-Request": "1", "Origin": "http://localhost:3000"}) as browser:
            return browser.post(
                "/auth/verify-email", json={"code": token, "challenge": client.verification_challenge}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: redeem(), range(2)))
    assert sorted(results) == [200, 400]


def test_smtp_adapter_uses_tls_and_does_not_log_link(monkeypatch, caplog):
    from app.services.account_mail import build_mail

    transport = Mock()
    connection = Mock()
    connection.__enter__ = Mock(return_value=transport)
    connection.__exit__ = Mock(return_value=False)
    factory = Mock(return_value=connection)
    monkeypatch.setattr("app.services.account_mail.smtplib.SMTP", factory)
    settings = Settings(
        _env_file=None,
        mail_delivery="smtp",
        smtp_host="smtp.example.test",
        mail_from="signal@example.test",
        smtp_username="test-user",
        smtp_password="test-mail-secret",
    )
    with caplog.at_level("INFO", logger="drive"):
        build_mail(settings).send(
            "customer@example.test", "verify", "https://signal.example.test/verify-email#token=example"
        )
    transport.starttls.assert_called_once()
    transport.login.assert_called_once_with("test-user", "test-mail-secret")
    transport.send_message.assert_called_once()
    assert "token=example" not in caplog.text and "test-mail-secret" not in caplog.text
