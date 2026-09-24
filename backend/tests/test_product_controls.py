import copy
from pathlib import Path
from unittest.mock import Mock
import pytest
from sqlalchemy import select, func, text, create_engine
from alembic import command
from alembic.config import Config
from app.models import (
    Call,
    User,
    EmployeeAssignment,
    Evaluation,
    Transcript,
    SpeakerCorrection,
    ScoreAdjustment,
    AdminEvent,
    PendingAudioDeletion,
    LEGACY_ORG,
)
from app.services.providers import DemoQA
from app.services.deletion import cleanup_audio
from .test_supervisor_controls import complete, other_tenant
from .test_employee_performance import employee, correct
from .test_hierarchy import edit, assign, team
from .test_batches import put


def published(client, name, categories):
    r = client.post(
        "/rubrics",
        json={
            "name": name,
            "categories": [
                {"name": label, "weight": weight, "criteria": "Check " + label, "description": ""}
                for label, weight in categories
            ],
        },
    )
    assert r.status_code == 201, r.text
    result = client.post(f"/rubrics/{r.json()['id']}/activate", json={"revision": 1})
    assert result.status_code == 200, result.text
    return result.json()


def role(app, value):
    with app.state.db() as db:
        db.scalar(select(User).where(User.email == "admin@example.test")).role = value
        db.commit()


def remove_employee(client, e):
    revision = client.get("/employees/" + e["id"]).json()["revision"]
    return client.request("DELETE", "/employees/" + e["id"], json={"revision": revision})


def test_explicit_manager_eligibility_removal_and_archive(signed_in):
    jon, report = employee(signed_in, "Jon"), employee(signed_in, "Report")
    sarah = signed_in.post("/employees", json={"name": "Sarah", "manager_eligible": True}).json()
    assert jon["manager_eligible"] is False
    assert [e["id"] for e in signed_in.get("/employees?managers_only=true&active=true").json()["items"]] == [
        sarah["id"]
    ]
    assert edit(signed_in, report, jon["id"]).status_code == 422
    assert edit(signed_in, jon, manager_eligible=True).status_code == 200
    assert edit(signed_in, report, jon["id"]).status_code == 200
    blocked = edit(signed_in, jon, manager_eligible=False)
    assert blocked.status_code == 409 and "1 direct reports" in blocked.text
    assert edit(signed_in, report, sarah["id"]).status_code == 200
    assert edit(signed_in, jon, manager_eligible=False).status_code == 200
    assert signed_in.post(f"/employees/{sarah['id']}/archive", json={"revision": 1}).status_code == 200
    assert signed_in.get("/employees?managers_only=true&active=true").json()["total"] == 0
    assert team(signed_in, sarah)["direct_reports"] == 1
    assert edit(signed_in, jon, sarah["id"]).status_code == 409


def test_two_selected_scorecards_control_provider_and_immutable_history(signed_in, app, wav_bytes):
    a = published(signed_in, "Customer Service QA", [("Greeting", 50), ("Closing", 50)])
    b = published(signed_in, "Sales QA", [("Verification", 70), ("Documentation", 30)])
    qa = Mock(name="qa", model="test")
    qa.name = "controlled"
    qa.evaluate.side_effect = lambda transcript, rubric=None, **kw: DemoQA().evaluate(transcript, rubric)
    app.state.processor.qa = qa
    r = signed_in.post("/calls", data={"rubric_id": a["id"]}, files={"file": ("selected.wav", wav_bytes, "audio/wav")})
    assert r.status_code == 201
    cid = r.json()["id"]
    with app.state.db() as db:
        assert db.get(Call, cid).requested_rubric_id == a["id"]
    app.state.processor.process(cid)
    first = signed_in.get("/calls/" + cid).json()
    original = copy.deepcopy(first["evaluation"])
    assert original["rubric_id"] == a["id"] and original["rubric_version"] == a["version"]
    assert [c["max_score"] for c in qa.evaluate.call_args.kwargs["rubric"]] == [50, 50]
    assert [c["max_score"] for c in original["categories"]] == [50, 50]
    transcriber = Mock()
    transcriber.name = "test"
    app.state.processor.transcription = transcriber
    assert (
        signed_in.post(
            f"/calls/{cid}/reevaluate", json={"rubric_id": b["id"], "evaluation_id": original["id"]}
        ).status_code
        == 200
    )
    app.state.processor.process(cid)
    history = signed_in.get(f"/calls/{cid}/evaluations").json()
    assert history[1] == original
    assert history[0]["rubric_name"] == "Sales QA" and history[0]["rubric_version"] == b["version"]
    assert [c["max_score"] for c in qa.evaluate.call_args.kwargs["rubric"]] == [70, 30]
    assert [c["max_score"] for c in history[0]["categories"]] == [70, 30]
    transcriber.transcribe.assert_not_called()
    # Archived versions remain valid only for explicit previous-scorecard correction.
    assert signed_in.post(f"/rubrics/{b['id']}/archive", json={"revision": b["revision"]}).status_code == 200
    payload = {"rubric_id": b["id"], "evaluation_id": history[0]["id"]}
    assert signed_in.post(f"/calls/{cid}/reevaluate", json=payload).status_code == 409
    revision = correct(signed_in, first)
    assert (
        signed_in.post(
            f"/calls/{cid}/reevaluate",
            json={**payload, "use_previous_scorecard": True, "transcript_revision": revision},
        ).status_code
        == 200
    )
    app.state.processor.process(cid)
    current = signed_in.get("/calls/" + cid).json()["evaluation"]
    assert current["rubric_id"] == b["id"] and current["transcript_revision"] == revision
    assert len(signed_in.get(f"/calls/{cid}/evaluations").json()) == 3
    transcriber.transcribe.assert_not_called()


def test_batch_scorecard_pin_idempotency_and_duplicate_conflict(signed_in, app, wav_bytes):
    a = published(signed_in, "Batch A", [("Greeting", 100)])
    b = published(signed_in, "Batch B", [("Closing", 100)])
    body = {
        "request_key": "selected-batch-key",
        "rubric_id": a["id"],
        "files": [{"filename": f"{i}.wav", "size_bytes": len(wav_bytes)} for i in range(2)],
    }
    batch = signed_in.post("/batches", json=body).json()
    assert batch["rubric_id"] == a["id"]
    assert signed_in.post("/batches", json={**body, "rubric_id": b["id"]}).status_code == 409
    for i in range(2):
        current = put(signed_in, batch, i, wav_bytes[:-1] + bytes([i])).json()
        cid = current["items"][i]["call_id"]
        app.state.processor.process(cid)
        assert signed_in.get("/calls/" + cid).json()["evaluation"]["rubric_id"] == a["id"]
    other = signed_in.post("/batches", json={**body, "request_key": "different-batch-key", "rubric_id": b["id"]}).json()
    conflict = put(signed_in, other, 0, wav_bytes[:-1] + b"\x00").json()["items"][0]
    assert conflict["status"] == "failed" and "different scorecard" in conflict["error"] and conflict["call_id"] is None


def test_scorecard_tenant_draft_archive_and_no_published(signed_in, app, wav_bytes):
    _, rid = other_tenant(app)

    def upload(rubric_id):
        return signed_in.post(
            "/calls", data={"rubric_id": rubric_id}, files={"file": ("x.wav", wav_bytes, "audio/wav")}
        )

    assert upload(rid).status_code == 404
    assert (
        signed_in.post(
            "/batches",
            json={
                "request_key": "foreign-card-request",
                "rubric_id": rid,
                "files": [{"filename": "x.wav", "size_bytes": len(wav_bytes)}],
            },
        ).status_code
        == 404
    )
    draft = signed_in.post("/rubrics", json={"name": "Draft", "categories": []}).json()
    assert upload(draft["id"]).status_code == 409
    current = signed_in.get("/rubrics").json()
    for card in current:
        assert signed_in.post(f"/rubrics/{card['id']}/archive", json={"revision": card["revision"]}).status_code == 200
    assert upload(current[0]["id"]).status_code == 409
    assert signed_in.get("/config").status_code == 200
    assert signed_in.get("/config").json()["active_rubric_id"] is None


@pytest.mark.parametrize("actor_role", ["OWNER", "ADMIN"])
def test_call_delete_all_dependencies_audio_batch_aggregates_and_audit(signed_in, app, wav_bytes, actor_role):
    role(app, actor_role)
    manager = signed_in.post("/employees", json={"name": "Manager", "manager_eligible": True}).json()
    person = employee(signed_in, "Employee")
    edit(signed_in, person, manager["id"])
    call = complete(signed_in, app, wav_bytes)
    assign(signed_in, call, person)
    correct(signed_in, call)
    qa = call["evaluation"]
    signed_in.post(
        f"/calls/{call['id']}/evaluations/{qa['id']}/categories/greeting",
        json={"revision": 0, "score": 0, "reason": "Test"},
    )
    batch = signed_in.post(
        "/batches",
        json={"request_key": "delete-batch-request", "files": [{"filename": "copy.wav", "size_bytes": len(wav_bytes)}]},
    ).json()
    assert put(signed_in, batch, 0, wav_bytes).json()["items"][0]["call_id"] == call["id"]
    with app.state.db() as db:
        path = app.state.settings.upload_dir / db.get(Call, call["id"]).storage_name
    assert path.exists()
    result = signed_in.delete("/calls/" + call["id"])
    assert result.status_code == 200 and result.json()["status"] == "deleted"
    assert not path.exists()
    assert signed_in.get("/calls/" + call["id"]).status_code == 404
    assert signed_in.get("/calls/" + call["id"] + "/audio").status_code == 404
    assert signed_in.get("/calls").json()["total"] == 0
    assert team(signed_in, manager)["performance"]["interactions"] == 0
    assert signed_in.get("/employees/" + person["id"]).json()["performance"]["interactions"] == 0
    tombstone = signed_in.get("/batches/" + batch["id"]).json()
    assert tombstone["counts"]["deleted"] == 1
    assert tombstone["items"][0]["filename"] == "Deleted interaction"
    assert put(signed_in, batch, 0, wav_bytes).status_code == 409
    with app.state.db() as db:
        for model in (
            Call,
            Transcript,
            Evaluation,
            SpeakerCorrection,
            ScoreAdjustment,
            EmployeeAssignment,
            PendingAudioDeletion,
        ):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
        audit = db.scalar(select(AdminEvent).where(AdminEvent.resource_id == call["id"]))
        assert audit.actor_id and audit.organization_id == LEGACY_ORG and audit.created_at
    assert signed_in.delete("/calls/" + call["id"]).status_code == 200  # safe repeated confirmation


def test_audio_failure_is_durable_and_retryable(signed_in, app, wav_bytes, monkeypatch):
    call = complete(signed_in, app, wav_bytes)
    real = Path.unlink

    def fail(path, *args, **kwargs):
        if path.parent == app.state.settings.upload_dir:
            raise PermissionError("test")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail)
    assert signed_in.delete("/calls/" + call["id"]).json()["status"] == "audio_deletion_pending"
    assert signed_in.get("/calls").json()["total"] == 0
    with app.state.db() as db:
        assert db.get(PendingAudioDeletion, call["id"]) is not None
    monkeypatch.setattr(Path, "unlink", real)
    assert cleanup_audio(app.state.db, app.state.settings, call["id"])
    assert signed_in.delete("/calls/" + call["id"]).json()["status"] == "deleted"


@pytest.mark.parametrize("actor_role", ["MANAGER", "REVIEWER", "SUPERVISOR", "EMPLOYEE"])
def test_delete_permission_matrix(signed_in, app, wav_bytes, actor_role):
    call = complete(signed_in, app, wav_bytes)
    e = employee(signed_in, "Unused")
    role(app, actor_role)
    assert signed_in.delete("/calls/" + call["id"]).status_code == 403
    assert signed_in.request("DELETE", "/employees/" + e["id"], json={"revision": 1}).status_code == 403
    assert signed_in.post("/employees/" + e["id"] + "/archive", json={"revision": 1}).status_code == 403
    assert signed_in.get("/admin/events").status_code == 403


def test_employee_unused_delete_history_block_archive_and_tenant(signed_in, app, wav_bytes):
    empty = employee(signed_in, "Accidental")
    assert remove_employee(signed_in, empty).status_code == 200
    person = employee(signed_in, "History")
    call = complete(signed_in, app, wav_bytes)
    assign(signed_in, call, person)
    before = signed_in.get("/calls/" + call["id"]).json()
    blocked = remove_employee(signed_in, person)
    assert blocked.status_code == 409 and "1 interactions" in blocked.text and "assignment-history" in blocked.text
    assert signed_in.post("/employees/" + person["id"] + "/archive", json={"revision": 1}).status_code == 200
    assert signed_in.get("/employees?active=true").json()["total"] == 0
    assert signed_in.get("/calls/" + call["id"]).json()["evaluation"] == before["evaluation"]
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.delete("/calls/" + call["id"]).status_code == 404
    assert signed_in.request("DELETE", "/employees/" + person["id"], json={"revision": 2}).status_code == 404
    assert signed_in.post("/employees/" + person["id"] + "/archive", json={"revision": 2}).status_code == 404
    assert signed_in.get("/admin/events").json() == []


def test_inflight_delete_blocked_and_queued_delete_cannot_run(signed_in, app, wav_bytes):
    call = signed_in.post("/calls", files={"file": ("queued.wav", wav_bytes, "audio/wav")}).json()
    with app.state.db() as db:
        db.get(Call, call["id"]).status = "analyzing"
        db.commit()
    assert signed_in.delete("/calls/" + call["id"]).status_code == 409
    with app.state.db() as db:
        db.get(Call, call["id"]).status = "queued"
        db.commit()
    assert signed_in.delete("/calls/" + call["id"]).status_code == 200
    app.state.processor.process(call["id"])
    assert signed_in.get("/calls").json()["total"] == 0


def test_employee_report_link_and_unassigned_history_block_deletion(signed_in, app, wav_bytes):
    manager = signed_in.post("/employees", json={"name": "Manager", "manager_eligible": True}).json()
    report = employee(signed_in, "Report")
    edit(signed_in, report, manager["id"])
    assert "direct reports" in remove_employee(signed_in, manager).text
    edit(signed_in, report)
    assert "reporting/link-history" in remove_employee(signed_in, manager).text
    linked = employee(signed_in, "Linked")
    with app.state.db() as db:
        uid = db.scalar(select(User.id).where(User.email == "admin@example.test"))
    signed_in.put("/employees/" + linked["id"] + "/user-link", json={"user_id": uid, "revision": 1})
    assert "linked login accounts" in remove_employee(signed_in, linked).text
    historical = employee(signed_in, "Historical")
    call = complete(signed_in, app, wav_bytes)
    assign(signed_in, call, historical)
    assign(signed_in, call, None)
    blocked = remove_employee(signed_in, historical)
    assert blocked.status_code == 409 and "assignment-history" in blocked.text


def test_selected_contract_rejects_provider_using_wrong_scorecard(signed_in, app, wav_bytes):
    card = published(signed_in, "Selected custom", [("Verification", 70), ("Documentation", 30)])
    qa = Mock(model="test")
    qa.name = "wrong-contract"
    qa.evaluate.side_effect = lambda transcript, **kwargs: DemoQA().evaluate(transcript)
    app.state.processor.qa = qa
    result = signed_in.post(
        "/calls", data={"rubric_id": card["id"]}, files={"file": ("contract.wav", wav_bytes, "audio/wav")}
    )
    app.state.processor.process(result.json()["id"])
    detail = signed_in.get("/calls/" + result.json()["id"]).json()
    assert detail["status"] == "failed" and detail["transcript"] is not None and detail["evaluation"] is None
    assert "category" in detail["error"]


def test_migration_designates_only_existing_managers(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "upgrade.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "i957358dfa08")
    engine = create_engine(url)
    with engine.begin() as db:
        for eid in ["manager", "report", "normal"]:
            db.execute(
                text(
                    "INSERT INTO employees (id,organization_id,name,title,active,revision,created_at) VALUES (:id,:org,:id,'',1,1,1)"
                ),
                {"id": eid, "org": LEGACY_ORG},
            )
        db.execute(text("UPDATE employees SET manager_id='manager' WHERE id='report'"))
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as db:
        rows = {
            r.id: (r.manager_id, r.manager_eligible)
            for r in db.execute(text("SELECT id,manager_id,manager_eligible FROM employees"))
        }
        assert rows == {"manager": (None, 1), "report": ("manager", 0), "normal": (None, 0)}
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()
