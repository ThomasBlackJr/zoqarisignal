from unittest.mock import Mock
import time
import pytest
from sqlalchemy import select
from app.models import Call, FlagNotification, User
from app.services.flags import matches, detect, deliver_one
from .test_supervisor_controls import complete, other_tenant, supervisor
from .test_employee_performance import correct, employee
from .test_hierarchy import assign


@pytest.mark.parametrize(
    "text,phrase,count",
    [
        ("Cancel, CANCEL! cancellation canceled.", "cancel", 2),
        ("Speak to a manager. speak, to—a manager!", "speak to a manager", 2),
        ("refund refund refund", "refund", 3),
        ("scattered cat caterpillar", "cat", 1),
        ("BBB bbb", "bbb", 2),
        ("café CAFÉ", "café", 2),
        ("a a a", "a a", 2),
    ],
)
def test_word_phrase_offsets(text, phrase, count):
    result = matches(text, phrase)
    assert len(result) == count
    assert all(0 <= start < end <= len(text) for start, end in result)


def rule(client, app, phrase="delivery", notify=False):
    with app.state.db() as db:
        uid = db.scalar(select(User.id).where(User.email == "admin@example.test"))
    r = client.post("/flag-rules", json={"phrase": phrase, "notify": notify, "recipients": [uid] if notify else []})
    assert r.status_code == 201, r.text
    return r.json()


def test_revision_evidence_and_notification_idempotency(signed_in, app, wav_bytes):
    rule(signed_in, app, notify=True)
    call = complete(signed_in, app, wav_bytes)
    assert call["audit_number"].startswith("SIG-") and call["flagged"]
    flags = signed_in.get(f"/calls/{call['id']}/flags").json()
    assert len(flags["items"]) == 1 and len(flags["items"][0]["matches"]) > 1
    with app.state.db() as db:
        detect(db, db.get(Call, call["id"]))
        db.commit()
        assert len(db.scalars(select(FlagNotification)).all()) == 1
    correct(signed_in, call)
    latest = signed_in.get(f"/calls/{call['id']}/flags").json()
    assert latest["transcript_revision"] > 0
    assert len(latest["items"]) == 1
    assert len(signed_in.get(f"/calls/{call['id']}/flags?history=true").json()["items"]) == 2
    with app.state.db() as db:
        assert len(db.scalars(select(FlagNotification)).all()) == 1
    mail = Mock()
    deliver_one(app.state.db, app.state.settings, mail)
    deliver_one(app.state.db, app.state.settings, mail)
    assert mail.send.call_count == 1
    payload = mail.send.call_args.args[2]
    assert call["audit_number"] in payload and "delivery" in payload
    assert call["transcript"]["text"] not in payload


def test_filters_reference_and_disabled_rule(signed_in, app, wav_bytes):
    r = rule(signed_in, app)
    call = complete(signed_in, app, wav_bytes)
    e = employee(signed_in, "Employee")
    assign(signed_in, call, e)
    query = f"/calls?q={call['audit_number']}&flagged=true&status=completed&employee_id={e['id']}&rubric_id={call['evaluation']['rubric_id']}&date_from=1&date_to={time.time() + 1}"
    assert signed_in.get(query).json()["total"] == 1
    assert signed_in.get(query + "&outdated=true").json()["total"] == 0
    correct(signed_in, call)
    assert signed_in.get(query + "&outdated=true&needs_review=true").json()["total"] == 1
    assert (
        signed_in.put(
            "/flag-rules/" + r["id"], json={k: v for k, v in {**r, "enabled": False}.items() if k != "id"}
        ).status_code
        == 200
    )
    assert signed_in.get("/calls?flagged=true").json()["total"] == 0
    assert signed_in.get(f"/calls/{call['id']}/flags?history=true").json()["items"]
    assert signed_in.get("/calls?date_from=5&date_to=1").status_code == 422
    other = complete(signed_in, app, wav_bytes)
    assert other["audit_number"] != call["audit_number"]
    assert signed_in.delete("/calls/" + call["id"]).status_code == 200
    assert signed_in.get("/calls?q=" + call["audit_number"]).json()["total"] == 0


def test_cross_org_rules_matches_recipients_and_notifications(signed_in, app, wav_bytes):
    r = rule(signed_in, app, notify=True)
    call = complete(signed_in, app, wav_bytes)
    n = signed_in.get("/flag-notifications").json()[0]
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/flag-rules").json()["items"] == []
    assert signed_in.get("/flag-notifications").json() == []
    assert signed_in.get(f"/calls/{call['id']}/flags").status_code == 404
    assert signed_in.get("/calls?q=" + call["audit_number"]).json()["total"] == 0
    assert signed_in.put("/flag-rules/" + r["id"], json={k: v for k, v in r.items() if k != "id"}).status_code == 404
    assert (
        signed_in.post(
            "/flag-rules", json={"phrase": "other", "notify": True, "recipients": r["recipients"]}
        ).status_code
        == 404
    )
    assert signed_in.post("/flag-notifications/" + n["id"] + "/retry").status_code == 404
    supervisor(signed_in)
    assert signed_in.get("/flag-rules").status_code == 403
    assert signed_in.post("/flag-rules", json={"phrase": "attorney"}).status_code == 403


def test_mail_uncertain_requires_explicit_retry_and_no_secret_log(signed_in, app, wav_bytes, caplog):
    rule(signed_in, app, notify=True)
    complete(signed_in, app, wav_bytes)
    mail = Mock()
    mail.send.side_effect = RuntimeError("PRIVATE SMTP SECRET")
    deliver_one(app.state.db, app.state.settings, mail)
    deliver_one(app.state.db, app.state.settings, mail)
    assert mail.send.call_count == 1
    n = signed_in.get("/flag-notifications").json()[0]
    assert n["status"] == "uncertain" and "PRIVATE SMTP SECRET" not in caplog.text
    assert signed_in.post("/flag-notifications/" + n["id"] + "/retry").status_code == 200
    mail.send.side_effect = None
    deliver_one(app.state.db, app.state.settings, mail)
    assert signed_in.get("/flag-notifications").json()[0]["status"] == "local"
