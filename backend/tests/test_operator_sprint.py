"""Synthetic fixtures only; no paid providers or normal local database."""

from unittest.mock import Mock
import pytest
from alembic import command
from alembic.config import Config
from app.db import make_database
from app.models import Transcript, Employee
from app.services.conversations import ConversationService
from app.services.speaker_roles import operator_context
from app.services.flags import matches
from .test_employee_performance import employee
from .test_supervisor_controls import other_tenant, supervisor, complete
from .test_batches import put
from .test_flags import rule


def batch(client, eid=None, key="operator-batch-0001"):
    return client.post(
        "/batches",
        json={
            "employee_id": eid,
            "request_key": key,
            "files": [{"filename": "one.wav", "size_bytes": 16044}, {"filename": "two.wav", "size_bytes": 16044}],
        },
    )


@pytest.mark.parametrize("assigned", [True, False])
def test_operator_manifest_partial_retry_and_individual_reassignment(signed_in, app, wav_bytes, assigned):
    e = employee(signed_in, "Alex Morgan")
    eid = e["id"] if assigned else None
    response = batch(signed_in, eid)
    assert response.status_code == 201
    b = response.json()
    assert batch(signed_in, eid).json()["id"] == b["id"]
    assert batch(signed_in, None if assigned else e["id"]).status_code == 409
    put(signed_in, b, 0, wav_bytes)
    failed = put(signed_in, b, 1, b"invalid").json()
    assert failed["counts"]["failed"] == 1
    result = put(signed_in, b, 1, wav_bytes[:-1] + b"x").json()
    assert result["counts"]["queued"] == 2
    for item in result["items"]:
        app.state.processor.process(item["call_id"])
        call = signed_in.get("/calls/" + item["call_id"]).json()
        assert call["employee_id"] == eid
        assert call["status"] == "completed"
        if assigned:
            assert call["evaluation"]["transcript_context"]["operator"]["id"] == eid
        history = signed_in.get(f"/calls/{call['id']}/assignments").json()
        assert len(history) == int(assigned)
    cid = result["items"][0]["call_id"]
    call = signed_in.get("/calls/" + cid).json()
    assert (
        signed_in.post(
            f"/calls/{cid}/assignment",
            json={"employee_id": None if assigned else e["id"], "revision": call["assignment_revision"]},
        ).status_code
        == 200
    )
    duplicate = batch(signed_in, eid, "operator-batch-0002").json()
    put(signed_in, duplicate, 0, wav_bytes)
    assert signed_in.get("/calls/" + cid).json()["employee_id"] == (None if assigned else e["id"])


def test_operator_validation_tenant_roles_archival_and_single_upload(signed_in, app, wav_bytes):
    e = employee(signed_in, "Alex Morgan")
    single = signed_in.post("/calls", data={"employee_id": e["id"]}, files={"file": ("one.wav", wav_bytes)})
    assert single.status_code == 201 and single.json()["employee_id"] == e["id"]
    assert batch(signed_in, "missing").status_code == 404
    assert batch(signed_in, "").status_code == 422
    b = batch(signed_in, e["id"]).json()
    assert signed_in.request("DELETE", "/employees/" + e["id"], json={"revision": 1}).status_code == 409
    with app.state.db() as db:
        db.get(Employee, e["id"]).active = False
        db.commit()
    assert put(signed_in, b, 0, wav_bytes[:-1] + b"y").json()["counts"]["failed"] == 1
    with app.state.db() as db:
        db.get(Employee, e["id"]).active = True
        db.commit()
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert batch(signed_in, e["id"]).status_code == 404
    assert (
        signed_in.post("/calls", data={"employee_id": e["id"]}, files={"file": ("one.wav", wav_bytes)}).status_code
        == 404
    )
    supervisor(signed_in)
    assert batch(signed_in, e["id"], "new-supervisor-key").status_code == 403


def turns(parts):
    text = " ".join(t for _, t in parts)
    segments = [{"text": t, "speaker": s, "start": i * 2, "end": i * 2 + 1} for i, (s, t) in enumerate(parts)]
    return text, segments, ConversationService().derive(text, segments).model_dump(mode="json")["turns"]


def test_operator_roles_follow_identity_not_order_and_keep_unknown():
    _, _, view = turns(
        [
            ("customer", "I'm calling about my delivery."),
            ("agent", "This is Alex Morgan."),
            ("customer", "It is late."),
            ("agent", "Let me check."),
            ("third", "Okay."),
        ]
    )
    operator_context(view, "Alex Morgan")
    assert [t["speaker_role"] for t in view] == ["CALLER", "DISPATCHER", "CALLER", "DISPATCHER", "UNKNOWN"]
    assert view[3]["operator_identity_supported"]


@pytest.mark.parametrize(
    "parts",
    [
        [(None, "Hello."), (None, "Okay.")],
        [("one", "This is Alex Morgan."), ("two", "This is Alex Morgan.")],
        [("one", "This is Alex Morgan. I'm calling about my delivery.")],
        [(None, "The agent said this is Alex Morgan.")],
    ],
)
def test_operator_assignment_is_not_proof(parts):
    _, _, view = turns(parts)
    operator_context(view, "Alex Morgan")
    assert not any(t.get("operator_identity_supported") for t in view)


def test_operator_context_manual_override_and_initial_qa(signed_in, app, wav_bytes):
    e = employee(signed_in, "Alex Morgan")
    cid = signed_in.post("/calls", data={"employee_id": e["id"]}, files={"file": ("one.wav", wav_bytes)}).json()["id"]
    text, segments, _ = turns(
        [
            ("caller", "I'm calling about my delivery."),
            ("agent", "This is Alex Morgan."),
            ("caller", "Thanks."),
            ("agent", "I don't know."),
        ]
    )
    with app.state.db() as db:
        db.add(Transcript(call_id=cid, text=text, segments=segments, provider="fixture", model="fixture"))
        db.commit()
    qa = Mock(name="qa")
    qa.name, qa.model = "fixture", "fixture"
    # Capture context, then deliberately fail before materialization to avoid invented QA evidence.
    qa.evaluate.side_effect = RuntimeError("test failure")
    app.state.processor.qa = qa
    app.state.processor.transcription = Mock()
    app.state.processor.transcription.name = "fixture"
    app.state.processor.process(cid)
    context = qa.evaluate.call_args.kwargs["speaker_context"]
    assert context["revision"] == 0 and context["operator"]["id"] == e["id"]
    assert context["turns"][1]["label"] == "Alex Morgan — Agent"
    detail = signed_in.get("/calls/" + cid).json()
    conv = detail["transcript"]["conversation"]
    t = conv["turns"][1]
    assert (
        signed_in.post(
            f"/calls/{cid}/speakers",
            json={
                "source_fingerprint": conv["source_fingerprint"],
                "source_start": t["source_start"],
                "source_end": t["source_end"],
                "role": "CALLER",
                "scope": "speaker",
                "revision": conv["revision"],
            },
        ).status_code
        == 200
    )
    corrected = signed_in.get("/calls/" + cid).json()["transcript"]["conversation"]
    assert all(t["effective_role"] == "CALLER" for t in corrected["turns"] if t["speaker_id"] == "agent")
    assert "".join(t["text"] for t in corrected["turns"]) == text
    from app.services.performance import snapshot_context

    with app.state.db() as db:
        context = snapshot_context(db, db.get(Transcript, cid))
        assert context["revision"] > 0
        assert all(t["role"] == "CALLER" and t["manual"] for t in context["turns"] if t["speaker_id"] == "agent")
    app.state.processor.transcription.transcribe.assert_not_called()


@pytest.mark.parametrize(
    "text,phrase,count",
    [
        ("I don't know. I DON’T KNOW!", "I don't know", 2),
        ("No refund requested.", "refund", 1),
        ("refunded", "refund", 0),
        ("Where, is—the driver?", "where is the driver", 1),
    ],
)
def test_flag_matching_examples(text, phrase, count):
    assert len(matches(text, phrase)) == count


def test_flag_edit_delete_preserves_history_and_new_calls(signed_in, app, wav_bytes):
    r = rule(signed_in, app, phrase="delivery", notify=True)
    call = complete(signed_in, app, wav_bytes)
    before = signed_in.get(f"/calls/{call['id']}/flags?history=true").json()["items"]
    assert before[0]["matches"][0]["start"] is None  # Fixture contains no timestamps; never invent them.
    body = {k: v for k, v in r.items() if k != "id"}
    edited = signed_in.put("/flag-rules/" + r["id"], json={**body, "phrase": "driver"}).json()
    assert not signed_in.get(f"/calls/{call['id']}/flags").json()["items"]
    assert signed_in.get(f"/calls/{call['id']}/flags?history=true").json()["items"] == before
    newly_processed = complete(signed_in, app, wav_bytes)
    assert signed_in.get(f"/calls/{newly_processed['id']}/flags").json()["items"][0]["phrase"] == "driver"
    assert signed_in.request("DELETE", "/flag-rules/" + r["id"], json={"revision": 1}).status_code == 409
    assert (
        signed_in.request("DELETE", "/flag-rules/" + r["id"], json={"revision": edited["revision"]}).status_code == 200
    )
    assert not signed_in.get("/flag-rules").json()["items"]
    history = signed_in.get(f"/calls/{call['id']}/flags?history=true").json()["items"]
    assert history[0]["matches"] == before[0]["matches"] and history[0]["rule_deleted"]
    newer = complete(signed_in, app, wav_bytes)
    assert not signed_in.get(f"/calls/{newer['id']}/flags?history=true").json()["items"]
    replacement = rule(signed_in, app, phrase="driver")
    assert replacement["id"] != r["id"]
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.request("DELETE", "/flag-rules/" + replacement["id"], json={"revision": 1}).status_code == 404


def test_migration_preserves_old_rows_and_guards_downgrade(tmp_path, monkeypatch):
    value = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", value)
    config = Config("alembic.ini")
    command.upgrade(config, "o513914dea14")
    engine, _ = make_database(value)
    with engine.connect() as conn:
        before = conn.exec_driver_sql("SELECT * FROM rubrics").all()
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT * FROM rubrics").all() == before
    command.downgrade(config, "o513914dea14")
    command.upgrade(config, "head")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO users (id,email,name,password_hash,role,active,organization_id,email_verified) VALUES ('test-user','migration@example.test','Migration','unused','ADMIN',1,'00000000-0000-0000-0000-000000000002',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO flag_rules (id,organization_id,phrase,enabled,severity,notify,recipients,revision,created_by,created_at,deleted_at) VALUES ('test-rule','00000000-0000-0000-0000-000000000002','test',0,'info',0,'[]',2,'test-user',0,1)"
        )
    with pytest.raises(RuntimeError, match="deletion history"):
        command.downgrade(config, "o513914dea14")
    engine.dispose()


def test_phrase_timestamps_span_all_matched_turns(signed_in, app, wav_bytes):
    rule(signed_in, app, phrase="I don't know")
    cid = signed_in.post("/calls", files={"file": ("one.wav", wav_bytes)}).json()["id"]
    with app.state.db() as db:
        db.add(
            Transcript(
                call_id=cid,
                text="I don't know. I DON'T KNOW!",
                provider="fixture",
                model="fixture",
                segments=[
                    {"text": "I don't", "speaker": "a", "start": 1, "end": 2},
                    {"text": "know.", "speaker": "b", "start": 3, "end": 4},
                    {"text": "I DON'T KNOW!", "speaker": "a", "start": 5, "end": 6},
                ],
            )
        )
        db.commit()
    assert signed_in.post("/flag-rules/scan-existing").status_code == 200
    found = signed_in.get(f"/calls/{cid}/flags").json()["items"][0]["matches"]
    assert len(found) == 2
    assert (found[0]["start"], found[0]["end"]) == (1, 4)
    assert (found[1]["start"], found[1]["end"]) == (5, 6)
    assert (found[0]["source_start"], found[0]["source_end"]) == (0, 12)
