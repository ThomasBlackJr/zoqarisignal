import time
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.auth import COOKIE, token_hash
from app.models import Call, Session, Status, User
from app.schemas import Segment, Transcription
from app.services.providers import DEMO_LINES, DemoQA
from app.services.rubric import validate_result


def upload(client, audio, name="dispatch.wav"):
    return client.post("/calls", files={"file": (name, audio, "audio/wav")})


def test_authentication_session_revocation_and_expiry(client, app):
    assert client.get("/calls").status_code == 401
    assert client.post("/auth/login", json={"email": "admin@example.test", "password": "wrong"}).status_code == 401
    response = client.post("/auth/login", json={"email": "ADMIN@example.test", "password": "test-password-only"})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    token = client.cookies.get(COOKIE)
    with app.state.db() as db:
        session = db.get(Session, token_hash(token))
        assert session is not None and session.token_hash != token
        assert db.scalar(select(User)).password_hash.startswith("$argon2id$")
    assert client.get("/auth/me").json()["role"] == "ADMIN"
    assert client.post("/auth/logout").status_code == 204
    client.cookies.set(COOKIE, token)
    assert client.get("/auth/me").status_code == 401
    with app.state.db() as db:
        user = db.scalar(select(User))
        db.add(Session(token_hash=token_hash(token), user_id=user.id, expires_at=time.time() - 1))
        db.commit()
    assert client.get("/auth/me").status_code == 401


def test_roles_and_csrf(client):
    client.post("/auth/login", json={"email": "supervisor@example.test", "password": "test-password-only"})
    body = {"email": "new@example.test", "name": "New User", "password": "another-test-password", "role": "ADMIN"}
    assert client.post("/users", json=body).status_code == 403
    assert client.get("/dashboard").status_code == 200
    assert client.post("/auth/logout", headers={"Origin": "https://untrusted.test"}).status_code == 403
    assert client.post("/auth/logout", headers={"X-Drive-Request": ""}).status_code == 403


def test_admin_creates_user_and_duplicate(signed_in):
    body = {"email": "new@example.test", "name": "New User", "password": "another-test-password", "role": "SUPERVISOR"}
    response = signed_in.post("/users", json=body)
    assert response.status_code == 201
    assert "password_hash" not in response.json()
    assert signed_in.post("/users", json=body).status_code == 409
    body["password"] = "short"
    assert signed_in.post("/users", json=body).status_code == 422


@pytest.mark.parametrize(
    "name,data,code",
    [
        ("bad.exe", b"no", 422),
        ("fake.mp3", b"not audio", 422),
        ("broken.wav", b"RIFF1234WAVEbad", 422),
        ("empty.wav", b"", 422),
        ("huge.wav", b"x" * (1024 * 1024 + 1), 413),
    ],
    ids=["extension", "spoofed", "corrupt", "empty", "oversized"],
)
def test_file_validation_and_cleanup(signed_in, app, name, data, code):
    assert upload(signed_in, data, name).status_code == code
    assert list(app.state.processor.settings.upload_dir.iterdir()) == []
    assert signed_in.get("/calls").json()["total"] == 0


def test_end_to_end_persistence_search_dashboard_audio(signed_in, client, app, wav_bytes):
    result = upload(signed_in, wav_bytes, "../../dispatch.wav")
    assert result.status_code == 201
    call = result.json()
    assert call["filename"] == "dispatch.wav" and call["duration"] == 1
    assert signed_in.get("/dashboard").json()["awaiting"] == 1
    assert signed_in.get(f"/calls/{call['id']}/audio").content == wav_bytes
    ranged = signed_in.get(f"/calls/{call['id']}/audio", headers={"Range": "bytes=0-43"})
    assert ranged.status_code == 206 and ranged.content == wav_bytes[:44]
    app.state.processor.process(call["id"])
    detail = signed_in.get(f"/calls/{call['id']}").json()
    assert detail["status"] == "completed"
    assert detail["is_demo"] is True
    assert detail["transcript"]["text"] == "\n".join(DEMO_LINES)
    assert detail["evaluation"]["overall_score"] == 90
    assert len(detail["evaluation"]["categories"]) == 6
    assert signed_in.get("/calls?q=dispatch&status=completed").json()["total"] == 1
    assert signed_in.get("/calls?q=%").json()["total"] == 0
    assert signed_in.get("/calls?q=absent").json()["total"] == 0
    dashboard = signed_in.get("/dashboard").json()
    assert dashboard["processed"] == 1 and dashboard["average_score"] == 90
    assert signed_in.post(f"/calls/{call['id']}/retry").status_code == 409
    signed_in.post("/auth/logout")
    assert client.get(f"/calls/{call['id']}/audio").status_code == 401
    client.post("/auth/login", json={"email": "admin@example.test", "password": "test-password-only"})
    assert client.get(f"/calls/{call['id']}").json()["evaluation"]["overall_score"] == 90


def test_transcription_injection_timestamps_and_qa_retry(signed_in, app, wav_bytes):
    processor = app.state.processor
    transcript = Transcription(
        text="\n".join(DEMO_LINES), segments=[Segment(start=0, end=1, text=DEMO_LINES[0], speaker=None)]
    )
    fake = Mock(name="custom-transcriber")
    fake.name = "custom"
    fake.model = "test-model"
    fake.transcribe.return_value = transcript
    processor.transcription = fake
    processor.qa = Mock()
    processor.qa.evaluate.side_effect = ValueError("provider error with secret that must not be returned")
    call_id = upload(signed_in, wav_bytes).json()["id"]
    processor.process(call_id)
    detail = signed_in.get(f"/calls/{call_id}").json()
    assert detail["status"] == "failed" and detail["failed_stage"] == "qa"
    assert "secret" not in detail["error"]
    assert detail["transcript"]["segments"][0]["start"] == 0
    assert detail["transcript"]["provider"] == "custom"
    processor.qa = DemoQA()
    assert signed_in.post(f"/calls/{call_id}/retry").status_code == 200
    processor.process(call_id)
    assert signed_in.get(f"/calls/{call_id}").json()["status"] == "completed"
    fake.transcribe.assert_called_once()


def test_transcription_failure_and_restart_recovery(signed_in, app, wav_bytes):
    call_id = upload(signed_in, wav_bytes).json()["id"]
    app.state.processor.transcription = Mock()
    app.state.processor.transcription.transcribe.side_effect = RuntimeError("failed")
    app.state.processor.process(call_id)
    detail = signed_in.get(f"/calls/{call_id}").json()
    assert detail["status"] == "failed" and detail["transcript"] is None
    with app.state.db() as db:
        db.get(Call, call_id).status = Status.ANALYZING
        db.commit()
    app.state.processor.recover()
    detail = signed_in.get(f"/calls/{call_id}").json()
    assert detail["status"] == "failed" and "restart" in detail["error"]


@pytest.mark.parametrize("change", ["total", "maximum", "missing", "duplicate", "evidence", "negative", "type"])
def test_qa_validation(change):
    text = "\n".join(DEMO_LINES)
    data = DemoQA().evaluate(text).model_dump()
    if change == "total":
        data["overall_score"] = 1
    if change == "maximum":
        data["categories"][0]["max_score"] = 99
    if change == "missing":
        data["categories"].pop()
    if change == "duplicate":
        data["categories"][0]["key"] = "closing"
    if change == "evidence":
        data["categories"][0]["evidence"] = ["Invented quote"]
    if change == "negative":
        data["categories"][0]["score"] = -1
    if change == "type":
        data["overall_score"] = "90"
    with pytest.raises(ValueError):
        validate_result(data, text)


def test_malformed_qa_not_saved(signed_in, app, wav_bytes):
    call_id = upload(signed_in, wav_bytes).json()["id"]
    app.state.processor.qa = Mock()
    app.state.processor.qa.evaluate.return_value = {"overall_score": 150}
    app.state.processor.process(call_id)
    detail = signed_in.get(f"/calls/{call_id}").json()
    assert detail["status"] == "failed" and detail["evaluation"] is None and detail["transcript"] is not None


def test_not_found_and_invalid_filters(signed_in):
    assert signed_in.get("/calls/missing").status_code == 404
    assert signed_in.get("/calls?status=wrong").status_code == 422
    assert signed_in.get("/calls?offset=-1").status_code == 422
    assert signed_in.get("/health").json() == {"status": "ok"}


def test_login_rate_limit(client):
    for _ in range(10):
        assert client.post("/auth/login", json={"email": "nobody@example.test", "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"email": "nobody@example.test", "password": "wrong"}).status_code == 429
