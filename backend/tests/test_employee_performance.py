import copy
from unittest.mock import Mock

from app.models import Call, Transcript
from app.services.providers import DemoQA
from .test_supervisor_controls import complete, other_tenant, supervisor


def employee(client, name):
    response = client.post("/employees", json={"name": name, "title": "Dispatcher"})
    assert response.status_code == 201, response.text
    return response.json()


def correct(client, call, role="CALLER"):
    conv = client.get(f"/calls/{call['id']}").json()["transcript"]["conversation"]
    turn = conv["turns"][0]
    result = client.post(
        f"/calls/{call['id']}/speakers",
        json={
            "source_fingerprint": conv["source_fingerprint"],
            "source_start": turn["source_start"],
            "source_end": turn["source_end"],
            "role": role,
            "scope": "turn",
            "revision": conv["revision"],
        },
    )
    assert result.status_code == 200, result.text
    return result.json()["revision"]


def test_assignment_moves_current_performance_and_preserves_history(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    a, b = employee(signed_in, "Alex"), employee(signed_in, "Blair")
    path = f"/calls/{call['id']}/assignment"
    original = copy.deepcopy(call["evaluation"])
    for revision, target in enumerate([a["id"], b["id"], None]):
        assert signed_in.post(path, json={"employee_id": target, "revision": revision}).status_code == 200
        for e in [a, b]:
            p = signed_in.get("/employees/" + e["id"]).json()["performance"]
            assert p["analyzed"] == int(target == e["id"])
            assert p["signal_score"] == (90 if target == e["id"] else None)
        assert signed_in.get("/dashboard").json()["average_score"] == 90
        assert signed_in.get(f"/calls/{call['id']}").json()["evaluation"] == original
    assert len(signed_in.get(f"/calls/{call['id']}/assignments").json()) == 3
    assert signed_in.post(path, json={"employee_id": a["id"], "revision": 0}).status_code == 409
    assert signed_in.get("/calls?employee_id=unassigned").json()["total"] == 1
    assert signed_in.get("/calls?employee_id=" + a["id"]).json()["total"] == 0


def test_employee_edit_deactivation_permissions_and_tenant_scope(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    e = employee(signed_in, " Alex ")
    assert signed_in.get("/employees?q=Alex&active=true").json()["total"] == 1
    edited = dict(e, name="Alex updated", active=False)
    edited.pop("id")
    assert signed_in.put("/employees/" + e["id"], json=edited).status_code == 200
    assert signed_in.put("/employees/" + e["id"], json=edited).status_code == 409
    assert (
        signed_in.post(f"/calls/{call['id']}/assignment", json={"employee_id": e["id"], "revision": 0}).status_code
        == 409
    )
    assert signed_in.get("/employees?active=false").json()["total"] == 1
    supervisor(signed_in)
    assert signed_in.post("/employees", json={"name": "Forbidden"}).status_code == 403
    assert signed_in.put("/employees/" + e["id"], json=edited).status_code == 403
    assert (
        signed_in.post(f"/calls/{call['id']}/assignment", json={"employee_id": None, "revision": 0}).status_code == 403
    )
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/employees").json()["total"] == 0
    assert signed_in.get("/employees/" + e["id"]).status_code == 404
    assert signed_in.put("/employees/" + e["id"], json=edited).status_code == 404
    assert signed_in.get(f"/calls/{call['id']}/assignments").status_code == 404
    assert (
        signed_in.post(f"/calls/{call['id']}/assignment", json={"employee_id": None, "revision": 0}).status_code == 404
    )
    other = complete(signed_in, app, wav_bytes)
    assert (
        signed_in.post(f"/calls/{other['id']}/assignment", json={"employee_id": e["id"], "revision": 0}).status_code
        == 404
    )


def test_corrected_reevaluation_replaces_current_score_without_transcription(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    e = employee(signed_in, "Alex")
    signed_in.post(f"/calls/{call['id']}/assignment", json={"employee_id": e["id"], "revision": 0})
    original = copy.deepcopy(call["evaluation"])
    raw = copy.deepcopy(call["transcript"])
    revision = correct(signed_in, call)
    stale = signed_in.get(f"/calls/{call['id']}").json()
    assert stale["evaluation_stale"] and stale["qa_score"] is None
    assert signed_in.get("/dashboard").json()["average_score"] is None
    assert signed_in.get("/employees/" + e["id"]).json()["performance"]["stale"] == 1
    qa = Mock(name="qa", model="controlled-test")
    qa.name = "controlled-test"

    def evaluate(text, rubric=None, speaker_context=None):
        assert text == raw["text"]
        assert speaker_context["revision"] == revision
        assert speaker_context["turns"][0]["role"] == "CALLER"
        assert speaker_context["turns"][0]["manual"] is True
        result = DemoQA().evaluate(text, rubric)
        result.categories[0].score -= 2
        result.overall_score -= 2
        return result

    qa.evaluate.side_effect = evaluate
    app.state.processor.qa = qa
    app.state.processor.transcription.transcribe = Mock(side_effect=AssertionError("must reuse saved transcript"))
    body = {"rubric_id": original["rubric_id"], "evaluation_id": original["id"], "transcript_revision": revision}
    assert signed_in.post(f"/calls/{call['id']}/reevaluate", json={**body, "transcript_revision": 0}).status_code == 409
    assert signed_in.post(f"/calls/{call['id']}/reevaluate", json=body).status_code == 200
    assert signed_in.post(f"/calls/{call['id']}/reevaluate", json=body).status_code == 409
    app.state.processor.process(call["id"])
    current = signed_in.get(f"/calls/{call['id']}").json()
    assert current["qa_score"] == 88 and not current["evaluation_stale"]
    assert current["transcript"]["text"] == raw["text"] and current["transcript"]["segments"] == raw["segments"]
    assert current["evaluation"]["transcript_revision"] == revision
    assert signed_in.get("/dashboard").json()["average_score"] == 88
    assert signed_in.get("/employees/" + e["id"]).json()["performance"]["signal_score"] == 88
    history = signed_in.get(f"/calls/{call['id']}/evaluations").json()
    assert len(history) == 2 and history[1]["stale"]
    for key in ["id", "categories", "overall_score", "adjustments", "transcript_context"]:
        assert history[1][key] == original[key]
    qa.evaluate.assert_called_once()
    app.state.processor.transcription.transcribe.assert_not_called()


def test_pinned_context_survives_failure_and_later_corrections(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    revision = correct(signed_in, call)
    body = {
        "rubric_id": call["evaluation"]["rubric_id"],
        "evaluation_id": call["evaluation"]["id"],
        "transcript_revision": revision,
    }
    signed_in.post(f"/calls/{call['id']}/reevaluate", json=body)
    qa = Mock(model="controlled-test")
    qa.name = "controlled-test"
    qa.evaluate.side_effect = ValueError("private provider payload")
    app.state.processor.qa = qa
    app.state.processor.process(call["id"])
    failed = signed_in.get(f"/calls/{call['id']}").json()
    assert failed["status"] == "failed" and failed["transcript"]["text"] == call["transcript"]["text"]
    assert "private" not in failed["error"]
    correct(signed_in, call, "DISPATCHER")
    qa.evaluate.side_effect = lambda text, rubric=None, speaker_context=None: DemoQA().evaluate(text, rubric)
    signed_in.post(f"/calls/{call['id']}/retry")
    app.state.processor.process(call["id"])
    result = signed_in.get(f"/calls/{call['id']}").json()
    assert result["status"] == "completed" and result["evaluation"]["transcript_revision"] == revision
    assert result["evaluation_stale"] and signed_in.get("/dashboard").json()["average_score"] is None


def test_corrupt_pinned_source_fails_before_provider(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    signed_in.post(
        f"/calls/{call['id']}/reevaluate",
        json={"rubric_id": call["evaluation"]["rubric_id"], "evaluation_id": call["evaluation"]["id"]},
    )
    with app.state.db() as db:
        value = db.get(Call, call["id"])
        value.requested_transcript_context = {**value.requested_transcript_context, "source_fingerprint": "invalid"}
        db.commit()
    app.state.processor.qa.evaluate = Mock(side_effect=AssertionError("no provider request"))
    app.state.processor.process(call["id"])
    result = signed_in.get(f"/calls/{call['id']}").json()
    assert result["status"] == "failed" and "transcript_context_mismatch" in result["error"]
    app.state.processor.qa.evaluate.assert_not_called()
    with app.state.db() as db:
        assert db.get(Transcript, call["id"]).text == call["transcript"]["text"]
