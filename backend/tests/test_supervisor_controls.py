import copy
import time
from unittest.mock import Mock
import pytest
from app.models import Call, Transcript, Rubric, User, Organization, RubricCategory
from app.auth import hasher
from app.services.rubric import RUBRIC, validate_result
from app.services.qa_contract import response_format, materialize


def complete(client, app, audio):
    cid = client.post("/calls", files={"file": ("review.wav", audio, "audio/wav")}).json()["id"]
    app.state.processor.process(cid)
    return client.get(f"/calls/{cid}").json()


def draft(client, weight=100):
    return client.post(
        "/rubrics",
        json={
            "name": "Service standard",
            "categories": [
                {
                    "name": "Resolution",
                    "weight": weight,
                    "description": "Customer outcome",
                    "criteria": "Concrete next steps.",
                }
            ],
        },
    ).json()


def supervisor(client):
    assert (
        client.post(
            "/auth/login", json={"email": "supervisor@example.test", "password": "test-password-only"}
        ).status_code
        == 200
    )


def test_rubric_lifecycle_frozen_history_and_reevaluation_without_transcription(signed_in, app, wav_bytes):
    old = complete(signed_in, app, wav_bytes)
    original = copy.deepcopy(old["evaluation"])
    r = draft(signed_in, 85)
    assert r["status"] == "DRAFT" and r["total_weight"] == 85
    assert signed_in.post(f"/rubrics/{r['id']}/activate", json={"revision": 1}).status_code == 422
    body = {
        "name": r["name"],
        "revision": 1,
        "categories": [
            {
                "key": r["categories"][0]["key"],
                "name": "Outcome",
                "weight": 100,
                "criteria": "Verify next steps.",
                "description": "",
            }
        ],
    }
    edited = signed_in.put(f"/rubrics/{r['id']}", json=body)
    assert edited.status_code == 200
    assert signed_in.put(f"/rubrics/{r['id']}", json=body).status_code == 409
    assert signed_in.post(f"/rubrics/{r['id']}/activate", json={"revision": 2}).status_code == 200
    rubrics = signed_in.get("/rubrics").json()
    assert sum(r["status"] == "ACTIVE" for r in rubrics) == 2
    assert next(r for r in rubrics if r["id"] == original["rubric_id"])["status"] == "ACTIVE"
    assert signed_in.put(f"/rubrics/{r['id']}", json=body).status_code == 409
    assert signed_in.get(f"/calls/{old['id']}").json()["evaluation"] == original
    assert signed_in.post(f"/rubrics/{r['id']}/archive", json={"revision": 2}).status_code == 409  # stale revision
    transcriber = Mock()
    transcriber.name = "demo"
    transcriber.transcribe.side_effect = AssertionError("No retranscription")
    app.state.processor.transcription = transcriber
    assert (
        signed_in.post(
            f"/calls/{old['id']}/reevaluate", json={"rubric_id": r["id"], "evaluation_id": original["id"]}
        ).status_code
        == 200
    )
    app.state.processor.process(old["id"])
    new = signed_in.get(f"/calls/{old['id']}").json()
    assert new["status"] == "completed" and new["evaluation"]["rubric_id"] == r["id"]
    assert len(new["evaluation"]["categories"]) == 1
    assert new["transcript"]["text"] == old["transcript"]["text"]
    history = signed_in.get(f"/calls/{old['id']}/evaluations").json()
    assert len(history) == 2 and history[1] == original
    transcriber.transcribe.assert_not_called()


def test_duplicate_edit_order_and_archive(signed_in):
    first = signed_in.get("/rubrics").json()[0]
    duplicate = signed_in.post(f"/rubrics/{first['id']}/duplicate").json()
    assert duplicate["version"] != first["version"] and duplicate["status"] == "DRAFT"
    cats = [
        {k: c[k] for k in ("key", "name", "description", "weight", "criteria")}
        for c in reversed(duplicate["categories"])
    ]
    response = signed_in.put(
        f"/rubrics/{duplicate['id']}", json={"name": "Reordered", "revision": 1, "categories": cats}
    )
    assert response.status_code == 200 and response.json()["categories"][0]["name"] == "Closing"
    assert signed_in.post(f"/rubrics/{duplicate['id']}/archive", json={"revision": 2}).json()["status"] == "ARCHIVED"


@pytest.mark.parametrize("score", [-1, 21, True, 2.5, "20"])
def test_invalid_adjustment_scores(signed_in, app, wav_bytes, score):
    call = complete(signed_in, app, wav_bytes)
    qa = call["evaluation"]
    path = f"/calls/{call['id']}/evaluations/{qa['id']}/categories/professionalism"
    assert signed_in.post(path, json={"score": score, "reason": "Test", "revision": 0}).status_code == 422
    assert signed_in.get(f"/calls/{call['id']}").json()["evaluation"] == qa


def test_override_reset_reason_audit_and_review(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    qa = call["evaluation"]
    supervisor(signed_in)
    path = f"/calls/{call['id']}/evaluations/{qa['id']}/categories/professionalism"
    assert signed_in.post(path, json={"score": 20, "reason": "  ", "revision": 0}).status_code == 422
    changed = signed_in.post(path, json={"score": 20, "reason": "Verification confirmed.", "revision": 0}).json()
    assert changed["overall_score"] == 90 and changed["final_score"] == 92 and changed["has_overrides"]
    assert changed["categories"][1]["score"] == 18
    assert changed["adjustments"][0]["actor_name"] == "Test Supervisor"
    assert changed["adjustments"][0]["previous_score"] == 18
    assert signed_in.post(path, json={"score": 19, "reason": "Stale edit", "revision": 0}).status_code == 409
    reset = signed_in.post(
        path, json={"score": None, "reason": "Restore original assessment.", "revision": changed["revision"]}
    ).json()
    assert reset["final_score"] == 90 and not reset["has_overrides"] and len(reset["adjustments"]) == 2
    assert signed_in.get("/dashboard").json()["requiring_review"] == 1
    assert signed_in.get("/calls?needs_review=true").json()["total"] == 1
    assert (
        signed_in.post(
            f"/calls/{call['id']}/evaluations/{qa['id']}/review", json={"revision": reset["revision"] + 1}
        ).status_code
        == 200
    )
    assert signed_in.get("/dashboard").json()["requiring_review"] == 0
    assert signed_in.get("/calls?needs_review=true").json()["total"] == 0
    assert signed_in.get("/dashboard").json()["average_score"] == 90


def test_speaker_single_bulk_persistence_scope_and_reset(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    cid = call["id"]
    qa = copy.deepcopy(call["evaluation"])
    with app.state.db() as db:
        t = db.get(Transcript, cid)
        # Synthetic speaker IDs only. Non-adjacent A turns, B stays unrelated.
        t.segments = [dict(s, speaker="A" if i % 2 == 0 else "B") for i, s in enumerate(t.segments)]
        t.conversation = None
        db.commit()
        raw = copy.deepcopy(t.segments)
        text = t.text
    supervisor(signed_in)
    conv = signed_in.get(f"/calls/{cid}").json()["transcript"]["conversation"]
    turn = conv["turns"][0]
    body = dict(
        source_fingerprint=conv["source_fingerprint"],
        source_start=turn["source_start"],
        source_end=turn["source_end"],
        role="CALLER",
        scope="turn",
        revision=0,
    )
    response = signed_in.post(f"/calls/{cid}/speakers", json=body)
    assert response.status_code == 200
    value = response.json()
    assert value["turns"][0]["effective_role"] == "CALLER"
    assert value["turns"][0]["inferred_role"] == turn["speaker_role"]
    assert value["turns"][0]["corrector_name"] == "Test Supervisor"
    assert signed_in.post(f"/calls/{cid}/speakers", json=body).status_code == 409
    body.update(role="DISPATCHER", scope="speaker", revision=value["revision"])
    value = signed_in.post(f"/calls/{cid}/speakers", json=body).json()
    for t in value["turns"]:
        if t["speaker_id"] == "A":
            assert t["effective_role"] == "DISPATCHER" and t["manual_role"] == "DISPATCHER"
        else:
            assert t["manual_role"] is None
    body.update(role=None, revision=value["revision"])
    value = signed_in.post(f"/calls/{cid}/speakers", json=body).json()
    assert all(t["manual_role"] is None for t in value["turns"])
    saved = signed_in.get(f"/calls/{cid}").json()
    assert saved["transcript"]["segments"] == raw and saved["transcript"]["text"] == text
    assert saved["evaluation"]["stale"] is True
    assert saved["evaluation"]["current_transcript_revision"] == value["revision"]

    def immutable(v):
        return {k: x for k, x in v.items() if k not in {"stale", "current_transcript_revision"}}

    assert immutable(saved["evaluation"]) == immutable(qa) and len(value["history"]) > 2


def test_unknown_identity_cannot_bulk_correct_and_forged_span_rejected(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    conv = call["transcript"]["conversation"]
    t = conv["turns"][0]
    body = dict(
        source_fingerprint=conv["source_fingerprint"],
        source_start=t["source_start"],
        source_end=t["source_end"],
        role="CALLER",
        scope="speaker",
        revision=0,
    )
    assert signed_in.post(f"/calls/{call['id']}/speakers", json=body).status_code == 422
    body.update(scope="turn", source_end=99999)
    assert signed_in.post(f"/calls/{call['id']}/speakers", json=body).status_code == 422


def test_supervisor_cannot_manage_rubrics_and_anonymous_cannot_modify(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    r = draft(signed_in)
    supervisor(signed_in)
    assert signed_in.get("/rubrics").status_code == 200
    for action in ("duplicate", "activate", "archive"):
        assert signed_in.post(f"/rubrics/{r['id']}/{action}", json={"revision": 1}).status_code == 403
    assert (
        signed_in.put(f"/rubrics/{r['id']}", json={"name": "Forbidden", "categories": [], "revision": 1}).status_code
        == 403
    )
    assert signed_in.post("/rubrics", json={"name": "Forbidden", "categories": []}).status_code == 403
    signed_in.post("/auth/logout")
    assert signed_in.post(f"/calls/{call['id']}/speakers", json={}).status_code == 401
    assert (
        signed_in.post(
            f"/calls/{call['id']}/evaluations/{call['evaluation']['id']}/categories/greeting", json={}
        ).status_code
        == 401
    )


def other_tenant(app):
    with app.state.db() as db:
        org = Organization(
            name="Other organization",
            subscription_status="active",
            entitlement_source="development",
            entitlement_expires_at=time.time() + 86400,
        )
        db.add(org)
        db.flush()
        user = User(
            email="other@example.test",
            name="Other admin",
            email_verified=True,
            role="ADMIN",
            organization_id=org.id,
            password_hash=hasher.hash("test-password-only"),
        )
        rubric = Rubric(name="Other standard", version="1.0", status="ACTIVE", organization_id=org.id)
        rubric.categories = [
            RubricCategory(
                key="other",
                name="Other quality",
                description="",
                weight=100,
                criteria="Other criteria",
                display_order=0,
            )
        ]
        db.add_all([user, rubric])
        db.commit()
        return org.id, rubric.id


def test_tenant_isolation_reads_writes_audio_history_and_qa(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    r = draft(signed_in)
    org, rid = other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/calls").json()["total"] == 0
    assert signed_in.get("/calls?q=review&needs_review=true").json()["total"] == 0
    assert signed_in.get("/dashboard").json()["total"] == 0
    assert signed_in.get("/dashboard").json()["average_score"] is None
    assert [r["id"] for r in signed_in.get("/rubrics").json()] == [rid]
    assert signed_in.get("/config").json()["active_rubric_id"] == rid
    for suffix in ("", "/audio", "/evaluations"):
        assert signed_in.get(f"/calls/{call['id']}{suffix}").status_code == 404
    assert signed_in.get(f"/calls/{call['id']}/audio", headers={"Range": "bytes=0-43"}).status_code == 404
    assert signed_in.post(f"/calls/{call['id']}/retry").status_code == 404
    t = call["transcript"]["conversation"]["turns"][0]
    assert (
        signed_in.post(
            f"/calls/{call['id']}/speakers",
            json=dict(
                source_fingerprint=call["transcript"]["conversation"]["source_fingerprint"],
                source_start=t["source_start"],
                source_end=t["source_end"],
                role="CALLER",
                revision=0,
            ),
        ).status_code
        == 404
    )
    assert (
        signed_in.post(
            f"/calls/{call['id']}/evaluations/{call['evaluation']['id']}/categories/greeting",
            json={"score": 0, "reason": "attack", "revision": 0},
        ).status_code
        == 404
    )
    assert (
        signed_in.post(
            f"/calls/{call['id']}/reevaluate", json={"rubric_id": rid, "evaluation_id": call["evaluation"]["id"]}
        ).status_code
        == 404
    )
    for action in ("duplicate", "activate", "archive"):
        assert signed_in.post(f"/rubrics/{r['id']}/{action}", json={"revision": 1}).status_code in (404, 409)
    assert (
        signed_in.put(f"/rubrics/{r['id']}", json={"name": "Attack", "categories": [], "revision": 1}).status_code
        == 409
    )
    other = complete(signed_in, app, wav_bytes)
    assert other["evaluation"]["rubric_id"] == rid and len(other["evaluation"]["categories"]) == 1
    with app.state.db() as db:
        assert db.get(Call, other["id"]).organization_id == org
        assert db.get(Rubric, r["id"]).status == "DRAFT"
    signed_in.post("/auth/login", json={"email": "admin@example.test", "password": "test-password-only"})
    assert signed_in.get("/calls").json()["total"] == 1
    assert signed_in.get(f"/calls/{other['id']}").status_code == 404


def test_dynamic_schema_keeps_evidence_and_maximum_guards():
    rubric = [dict(key="c_new", label="New", criteria="Verify", max_score=100)]
    schema = response_format(1, rubric)
    wire = {
        "categories": {"c_new": {"score": 84, "explanation": "Supported", "evidence_ids": [0]}},
        "summary": "Review",
        "strengths": [],
        "coaching_opportunities": [],
    }
    result = materialize(wire, ["Exact words."], "Exact words.", schema, rubric)
    assert result.overall_score == 84
    with pytest.raises(ValueError):
        materialize(wire, ["Fabricated."], "Exact words.", schema, rubric)
    wire["categories"]["c_new"]["score"] = 101
    with pytest.raises(ValueError):
        materialize(wire, ["Exact words."], "Exact words.", schema, rubric)
    with pytest.raises(ValueError):
        validate_result(result, "Exact words.", RUBRIC)


def test_migration_preserves_original_users_calls_transcripts_and_qa(tmp_path, monkeypatch):
    import json
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from app.services.providers import DemoQA, DEMO_LINES
    from app.models import LEGACY_ORG

    url = f"sqlite:///{tmp_path / 'history.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "b192cb82ae01")
    engine = create_engine(url)
    transcript = "\n".join(DEMO_LINES)
    result = DemoQA().evaluate(transcript).model_dump()
    with engine.begin() as db:
        db.execute(text("INSERT INTO users VALUES ('u','test@example.test','Existing user','private-hash','ADMIN',1)"))
        db.execute(
            text(
                "INSERT INTO calls (id,filename,storage_name,content_type,size_bytes,created_at,status,is_demo,uploaded_by) VALUES ('c','existing.wav','existing.wav','audio/wav',1,10,'completed',0,'u')"
            )
        )
        db.execute(
            text(
                "INSERT INTO transcripts (call_id,text,segments,conversation,provider,model,created_at) VALUES ('c',:text,'[]',NULL,'openai','whisper-1',11)"
            ),
            {"text": transcript},
        )
        db.execute(
            text(
                "INSERT INTO qa_evaluations (call_id,overall_score,result,rubric_version,provider,model,created_at) VALUES ('c',90,:result,'1.0','openai','gpt-4o-mini',12)"
            ),
            {"result": json.dumps(result)},
        )
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))
    with engine.connect() as db:
        assert db.execute(text("SELECT text FROM transcripts WHERE call_id='c'")).scalar_one() == transcript
        row = db.execute(text("SELECT id,overall_score,result,rubric_version,created_at FROM qa_evaluations")).one()
        assert row[0] == "c" and row[1] == 90 and json.loads(row[2]) == result and row[3:] == ("1.0", 12)
        assert db.execute(text("SELECT password_hash FROM users")).scalar_one() == "private-hash"
        for table in ("calls", "users", "rubrics"):
            assert db.execute(text(f"SELECT organization_id FROM {table}")).scalar_one() == LEGACY_ORG
        assert not db.execute(text("PRAGMA foreign_key_check")).fetchall()
    engine.dispose()


def test_admin_cannot_assign_user_to_another_tenant(signed_in, app):
    org, _ = other_tenant(app)
    body = {
        "email": "new@example.test",
        "password": "test-password-only",
        "name": "New",
        "role": "ADMIN",
        "organization_id": org,
    }
    assert signed_in.post("/users", json=body).status_code == 422
    body.pop("organization_id")
    own = signed_in.get("/auth/me").json()["organization_id"]
    assert signed_in.post("/users", json=body).json()["organization_id"] == own


def test_cross_tenant_publish_does_not_archive_other_active_scorecard(signed_in, app):
    own_active = signed_in.get("/config").json()["active_rubric_id"]
    _, rid = other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    value = draft(signed_in)
    assert signed_in.post(f"/rubrics/{value['id']}/activate", json={"revision": 1}).status_code == 200
    with app.state.db() as db:
        assert db.get(Rubric, own_active).status == "ACTIVE"
        assert db.get(Rubric, rid).status == "ACTIVE"
