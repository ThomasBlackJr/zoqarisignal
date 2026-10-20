from sqlalchemy import select
from app.models import User, VerificationCode
from tests.test_customer_entry import mail_token, PASSWORD, EMAIL
import time
import json
from unittest.mock import Mock
import httpx
import pytest
from app.auth import token_hash, verify
from app.models import AccountToken
from app.config import Settings
from app.services.resend_mail import ResendMail


def test_anonymous_verification_attempt_limit_no_plaintext(client, app):
    result = client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": PASSWORD})
    code = mail_token(app)
    challenge = result.json()["challenge"]
    assert code not in result.text and "set-cookie" not in result.headers
    wrong = "000001" if code != "000001" else "000002"
    for _ in range(5):
        assert client.post("/auth/verify-email", json={"code": wrong, "challenge": challenge}).status_code == 400
    assert client.post("/auth/verify-email", json={"code": code, "challenge": challenge}).status_code == 400
    with app.state.db() as db:
        row = db.scalar(select(VerificationCode))
        assert row.attempts == 5 and row.code_hash.startswith("$argon2")
        assert row.challenge_hash != challenge
        row.sent_at -= 61
        db.commit()
    replacement = client.post("/auth/verification-code/resend", json={"challenge": challenge})
    assert replacement.status_code == 200
    assert client.post("/auth/verify-email", json={"code": code, "challenge": challenge}).status_code == 400
    assert (
        client.post(
            "/auth/verify-email", json={"code": mail_token(app), "challenge": replacement.json()["challenge"]}
        ).status_code
        == 200
    )
    assert client.get("/auth/me").json()["email_verified"]


def test_public_registration_does_not_disclose_existing_address(client, app):
    body = {"name": "Owner", "email": EMAIL, "password": PASSWORD}
    a = client.post("/auth/register", json=body)
    b = client.post("/auth/register", json={**body, "password": "different-long-password"})
    assert a.status_code == b.status_code == 201
    assert a.json().keys() == b.json().keys()
    assert a.json()["message"] == b.json()["message"]
    assert a.json()["challenge"] != b.json()["challenge"]
    with app.state.db() as db:
        assert len(db.scalars(select(User).where(User.email == EMAIL)).all()) == 1


def test_secure_six_digit_generation_hash_ttl_and_no_api_or_log_disclosure(client, app, monkeypatch, caplog):
    generator = Mock(return_value=7)
    monkeypatch.setattr("app.services.verification.secrets.randbelow", generator)
    result = client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": PASSWORD})
    generator.assert_called_once_with(1000000)
    assert mail_token(app) == "000007"
    assert "000007" not in result.text and "000007" not in caplog.text
    assert client.get("/auth/me").status_code == 401
    with app.state.db() as db:
        row = db.scalar(select(VerificationCode))
        assert row.expires_at - row.sent_at == 900
        assert row.code_hash.startswith("$argon2") and verify("000007", row.code_hash)
        assert row.challenge_hash == token_hash(result.json()["challenge"])


def test_success_deletes_code_and_replay_has_generic_error(client, app):
    result = client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": PASSWORD})
    body = {"code": mail_token(app), "challenge": result.json()["challenge"]}
    assert client.post("/auth/verify-email", json=body).status_code == 200
    with app.state.db() as db:
        assert db.scalar(select(VerificationCode)) is None
        assert db.scalar(select(User).where(User.email == EMAIL)).email_verified
    replay = client.post("/auth/verify-email", json=body)
    unknown = client.post("/auth/verify-email", json={**body, "challenge": "x" * 43})
    assert replay.status_code == unknown.status_code == 400 and replay.json() == unknown.json()


def test_expiry_and_resend_cooldown_and_ip_limit(client, app):
    result = client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": PASSWORD})
    challenge = result.json()["challenge"]
    assert client.post("/auth/verification-code/resend", json={"challenge": challenge}).status_code == 429
    with app.state.db() as db:
        db.scalar(select(VerificationCode)).expires_at = time.time() - 1
        db.commit()
    assert client.post("/auth/verify-email", json={"code": mail_token(app), "challenge": challenge}).status_code == 400
    # Unknown challenges use the same bounded IP limiter and generic public response.
    for _ in range(17):
        assert client.post("/auth/verification-code/resend", json={"challenge": "x" * 43}).status_code == 200
    assert client.post("/auth/verification-code/resend", json={"challenge": "x" * 43}).status_code == 429


@pytest.mark.parametrize("password", ["SafePass12!X", PASSWORD])
def test_registration_through_resend_uses_code_template_without_a_link(client, app, password):
    messages = []

    def handler(request):
        messages.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "synthetic-submission"})

    value = Settings(_env_file=None, mail_delivery="resend", resend_api_key="re_synthetic_verification_test")
    app.state.settings.mail_delivery = "resend"
    app.state.mail = ResendMail(value, transport=httpx.MockTransport(handler))
    response = client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": password})
    assert response.status_code == 201 and len(messages) == 1
    payload = messages[0]
    assert payload["from"] == "Zoqari Signal <AccountManagement@zoqari.com>"
    assert payload["subject"] == "Your Zoqari Signal verification code"
    import re

    code = re.search(r"Verification code: ([0-9]{6})", payload["text"])[1]
    assert code in payload["html"] and "font-size:32px" in payload["html"]
    assert "15 minutes" in payload["text"] and "15 minutes" in payload["html"]
    assert "<a " not in payload["html"] and "/verify-email#" not in payload["text"]
    assert code not in response.text
    assert (
        client.post("/auth/verify-email", json={"code": code, "challenge": response.json()["challenge"]}).status_code
        == 200
    )


@pytest.mark.parametrize("password", ["Short12!", "Abcdef12!XY", "😀😁😂😃😄😅"])
def test_short_registration_never_creates_user_code_or_resend_submission(client, app, password):
    submissions = []

    def handler(request):
        submissions.append(request)
        return httpx.Response(200, json={"id": "must-not-submit"})

    value = Settings(_env_file=None, mail_delivery="resend", resend_api_key="re_synthetic_verification_test")
    app.state.settings.mail_delivery = "resend"
    app.state.mail = ResendMail(value, transport=httpx.MockTransport(handler))
    result = client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": password})
    assert result.status_code == 422 and not submissions
    assert password not in result.text
    with app.state.db() as db:
        assert db.scalar(select(User).where(User.email == EMAIL)) is None
        assert db.scalar(select(VerificationCode)) is None


def test_legacy_verification_links_are_not_redeemed(client, app):
    client.post("/auth/register", json={"name": "Owner", "email": EMAIL, "password": PASSWORD})
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == EMAIL))
        db.add(
            AccountToken(
                user_id=user.id,
                token_hash=token_hash("legacy-verification-token"),
                purpose="verify",
                expires_at=time.time() + 1000,
            )
        )
        db.commit()
    assert client.post("/auth/verify-email", json={"token": "legacy-verification-token"}).status_code == 422
    with app.state.db() as db:
        assert not db.scalar(select(User).where(User.email == EMAIL)).email_verified


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "１２３４５６"])
def test_malformed_code_is_not_echoed(client, code):
    result = client.post("/auth/verify-email", json={"code": code, "challenge": "x" * 43})
    assert result.status_code == 422 and code not in result.text
