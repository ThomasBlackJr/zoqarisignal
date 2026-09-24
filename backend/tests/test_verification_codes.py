from sqlalchemy import select
from app.models import User, VerificationCode
from tests.test_customer_entry import mail_token, PASSWORD, EMAIL


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
