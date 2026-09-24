import copy
import json
from unittest.mock import Mock

import pytest
from sqlalchemy import select, event, create_engine, text
from alembic import command
from alembic.config import Config

from app.models import Call, Evaluation, User, LEGACY_ORG
from app.services.briefing import snapshot
from app.services.coaching import CoachingChoice
from app.services.providers import OpenAICoaching
from .test_supervisor_controls import complete, other_tenant
from .test_employee_performance import correct, employee
from .test_hierarchy import assign, edit
from .test_product_controls import published


def finding(client):
    data = client.get("/briefing").json()
    return next(i for i in data["issues"] if i["category_key"] == "professionalism")


def detail(client, issue):
    return client.get("/briefing/issues/" + issue["id"]).json()


def generate(client, issue, **options):
    d = detail(client, issue)
    return client.post(
        "/briefing/issues/" + issue["id"] + "/generate", json={"fingerprint": d["fingerprint"], **options}
    )


def test_counts_distinct_people_versions_and_override_reset(signed_in, app, wav_bytes):
    calls = [complete(signed_in, app, wav_bytes) for _ in range(3)]
    a, b = employee(signed_in, "Private Person A"), employee(signed_in, "Private Person B")
    assign(signed_in, calls[0], a)
    assign(signed_in, calls[1], a)
    assign(signed_in, calls[2], b)
    issue = finding(signed_in)
    assert (issue["occurrences"], issue["eligible"], issue["affected_employees"]) == (3, 3, 2)
    assert issue["percent"] == 100 and issue["limited_sample"]
    assert "evidence" not in issue
    path = f"/calls/{calls[0]['id']}/evaluations/{calls[0]['evaluation']['id']}/categories/professionalism"
    changed = signed_in.post(path, json={"score": 20, "reason": "Reviewed", "revision": 0})
    assert changed.status_code == 200, changed.text
    assert finding(signed_in)["occurrences"] == 2
    reset = signed_in.post(path, json={"score": None, "reason": "Reset", "revision": changed.json()["revision"]})
    assert reset.status_code == 200
    assert finding(signed_in)["occurrences"] == 3
    card = published(signed_in, "Different professionalism", [("Professionalism", 100)])
    complete(signed_in, app, wav_bytes)
    issues = signed_in.get("/briefing").json()["issues"]
    assert any(i["rubric_id"] == card["id"] and i["occurrences"] == 1 for i in issues)
    assert finding(signed_in)["occurrences"] == 3


def test_stale_superseded_failed_attempt_and_attention(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    with app.state.db() as db:
        old = db.get(Evaluation, call["evaluation"]["id"])
        result = copy.deepcopy(old.result)
        for c in result["categories"]:
            c["score"] = c["max_score"]
        result["overall_score"] = 100
        db.add(
            Evaluation(
                call_id=call["id"],
                rubric_id=old.rubric_id,
                overall_score=100,
                result=result,
                rubric_version=old.rubric_version,
                provider="test",
                model="test",
                created_at=old.created_at + 1,
                transcript_revision=0,
            )
        )
        db.get(Call, call["id"]).status = "failed"
        db.commit()
    data = signed_in.get("/briefing").json()
    assert data["signal_score"] == 100 and data["analyzed"] == 1 and data["issues"] == []
    assert data["needs_attention"] == 1 and data["failed"] == 1 and data["requiring_review"] == 1
    correct(signed_in, call)
    data = signed_in.get("/briefing").json()
    assert data["analyzed"] == 0 and data["stale"] == 1 and data["signal_score"] is None


def test_team_weighting_current_reports_and_no_n_plus_one(signed_in, app, wav_bytes):
    manager = signed_in.post("/employees", json={"name": "Manager", "manager_eligible": True}).json()
    a, b = employee(signed_in, "A"), employee(signed_in, "B")
    edit(signed_in, a, manager["id"])
    edit(signed_in, b, manager["id"])
    calls = [complete(signed_in, app, wav_bytes) for _ in range(3)]
    for c, person in zip(calls, [a, a, b]):
        assign(signed_in, c, person)
    with app.state.db() as db:
        e = db.get(Evaluation, calls[2]["evaluation"]["id"])
        payload = copy.deepcopy(e.result)
        payload["categories"][0]["score"] = 0
        payload["overall_score"] = 80
        e.result, e.overall_score = payload, 80
        db.commit()
    data = signed_in.get("/briefing").json()
    assert data["teams"][0]["score"] == 86.7
    assert data["teams"][0]["direct_reports"] == 2
    counts = []

    def count(*args):
        counts.append(1)

    event.listen(app.state.engine, "before_cursor_execute", count)
    try:
        with app.state.db() as db:
            snapshot(db, LEGACY_ORG)
        assert len(counts) <= 8
    finally:
        event.remove(app.state.engine, "before_cursor_execute", count)
    edit(signed_in, b)
    assert signed_in.get("/briefing").json()["teams"][0]["score"] == 90


def test_grounded_generation_cache_regeneration_and_invalidation(signed_in, app, wav_bytes):
    calls = [complete(signed_in, app, wav_bytes) for _ in range(5)]
    a = employee(signed_in, "PRIVATE EMPLOYEE NAME")
    assign(signed_in, calls[0], a)
    provider = Mock(model="test-model")
    provider.name = "test"
    provider.recommend.return_value = {"action": "review_examples", "tone": "concise"}
    app.state.coaching = provider
    issue = finding(signed_in)
    result = generate(signed_in, issue)
    assert result.status_code == 200, result.text
    context = provider.recommend.call_args.args[0]
    assert context["occurrences"] == 5 and context["affected_employees"] == 1
    assert context["requirement"] == issue["criteria"]
    serialized = json.dumps(context)
    assert "PRIVATE EMPLOYEE NAME" not in serialized and calls[0]["id"] not in serialized
    assert calls[0]["transcript"]["text"] not in serialized
    assert "quotes" not in serialized and "explanation" not in serialized
    assert issue["criteria"] in result.json()["body"]
    assert "PRIVATE EMPLOYEE NAME" not in result.text
    assert generate(signed_in, issue).json() == result.json()
    assert detail(signed_in, issue)["draft"] == result.json()
    assert finding(signed_in)["recommendation"] == result.json()["recommendation"]
    assert "synthetic demonstration" in result.json()["body"]
    assert provider.recommend.call_count == 1
    assert generate(signed_in, issue, regenerate=True).status_code == 200
    assert provider.recommend.call_count == 2
    old = detail(signed_in, issue)["fingerprint"]
    correct(signed_in, calls[0])
    assert detail(signed_in, issue)["draft"] is None
    assert finding(signed_in)["recommendation"] is None
    assert signed_in.post("/briefing/issues/" + issue["id"] + "/generate", json={"fingerprint": old}).status_code == 409
    assert generate(signed_in, issue).status_code == 409
    assert provider.recommend.call_count == 2


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("OWNER", True),
        ("ADMIN", True),
        ("MANAGER", True),
        ("REVIEWER", True),
        ("SUPERVISOR", True),
        ("EMPLOYEE", False),
    ],
)
def test_existing_role_boundary(signed_in, app, wav_bytes, role, allowed):
    complete(signed_in, app, wav_bytes)
    issue = finding(signed_in)
    with app.state.db() as db:
        db.scalar(select(User).where(User.email == "admin@example.test")).role = role
        db.commit()
    assert signed_in.get("/briefing").status_code == (200 if allowed else 403)
    assert signed_in.get("/briefing/issues/" + issue["id"]).status_code == (200 if allowed else 403)
    r = signed_in.post("/briefing/issues/" + issue["id"] + "/generate", json={"fingerprint": "a" * 64})
    assert r.status_code == (409 if allowed else 403)


def test_tenant_guessed_issue_and_cached_draft_isolation(signed_in, app, wav_bytes):
    for _ in range(5):
        complete(signed_in, app, wav_bytes)
    issue = finding(signed_in)
    assert generate(signed_in, issue).status_code == 200
    fingerprint = detail(signed_in, issue)["fingerprint"]
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/briefing").json()["issues"] == []
    assert signed_in.get("/briefing/issues/" + issue["id"]).status_code == 404
    assert (
        signed_in.post("/briefing/issues/" + issue["id"] + "/generate", json={"fingerprint": fingerprint}).status_code
        == 404
    )
    complete(signed_in, app, wav_bytes)
    assert issue["id"] not in {i["id"] for i in signed_in.get("/briefing").json()["issues"]}


def test_invalid_provider_output_logs_no_payload_and_does_not_cache(signed_in, app, wav_bytes, caplog):
    for _ in range(5):
        complete(signed_in, app, wav_bytes)
    issue = finding(signed_in)
    app.state.coaching = Mock()
    app.state.coaching.recommend.return_value = {"action": "Fire PRIVATE NAME", "tone": "warm", "policy": "fabricated"}
    r = generate(signed_in, issue)
    assert r.status_code == 502 and "PRIVATE NAME" not in r.text + caplog.text
    assert detail(signed_in, issue)["draft"] is None


def test_openai_coaching_structured_adapter_refusal_and_untrusted_context(app):
    adapter = OpenAICoaching.__new__(OpenAICoaching)
    adapter.client, adapter.model = Mock(), "configured-model"
    adapter.client.responses.parse.return_value.output_parsed = CoachingChoice(action="team_practice", tone="warm")
    assert adapter.recommend({"requirement": "untrusted"})["action"] == "team_practice"
    kwargs = adapter.client.responses.parse.call_args.kwargs
    assert kwargs["model"] == "configured-model" and kwargs["store"] is False
    assert kwargs["text_format"] is CoachingChoice and "untrusted" in kwargs["input"][0]["content"]
    adapter.client.responses.parse.return_value.output_parsed = None
    with pytest.raises(ValueError, match="coaching_output_missing"):
        adapter.recommend({})


def test_preference_upgrade_preserves_existing_layout_and_new_defaults(signed_in):
    new = signed_in.get("/preferences").json()
    assert new["modules"] == ["metrics", "attention", "issues", "teams", "coaching", "recommendations", "recent"]
    old = signed_in.put("/preferences", json={**new, "modules": ["review", "recent", "metrics"]}).json()
    assert signed_in.get("/preferences").json() == old
    saved = signed_in.put("/preferences", json={**old, "modules": old["modules"] + ["issues", "processing"]})
    assert saved.status_code == 200
    assert signed_in.put("/preferences", json=old).status_code == 409


def test_migration_preserves_saved_preferences(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "briefing.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "j068469efb09")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO users (id,organization_id,email,name,password_hash,role,active,email_verified) VALUES ('u',:org,'test@example.test','Test','test','ADMIN',1,1)"
            ),
            {"org": LEGACY_ORG},
        )
        db.execute(text("INSERT INTO user_preferences VALUES ('u','dark','[\"review\",\"metrics\"]',7)"))
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as db:
        assert tuple(db.execute(text("SELECT * FROM user_preferences")).one()) == (
            "u",
            "dark",
            '["review","metrics"]',
            7,
        )
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()


def test_inflight_context_change_and_deleted_evidence_invalidate_draft(signed_in, app, wav_bytes):
    calls = [complete(signed_in, app, wav_bytes) for _ in range(6)]
    person = employee(signed_in, "Private reassignment")
    issue = finding(signed_in)
    provider = Mock(model="test")
    provider.name = "test"

    def changed_context(context):
        with app.state.db() as db:
            db.get(Call, calls[0]["id"]).employee_id = person["id"]
            db.commit()
        return {"action": "team_practice", "tone": "warm"}

    provider.recommend.side_effect = changed_context
    app.state.coaching = provider
    assert generate(signed_in, issue).status_code == 409
    assert detail(signed_in, issue)["draft"] is None
    provider.recommend.side_effect = None
    provider.recommend.return_value = {"action": "team_practice", "tone": "warm"}
    assert generate(signed_in, issue).status_code == 200
    assert signed_in.delete("/calls/" + calls[0]["id"]).status_code == 200
    d = detail(signed_in, issue)
    assert d["draft"] is None and d["occurrences"] == 5
    assert calls[0]["id"] not in {e["id"] for e in d["evidence"]}


def test_evidence_pages_do_not_change_aggregate(signed_in, app, wav_bytes):
    for _ in range(26):
        complete(signed_in, app, wav_bytes)
    issue = finding(signed_in)
    first = detail(signed_in, issue)
    second = signed_in.get("/briefing/issues/" + issue["id"] + "?offset=25").json()
    assert first["occurrences"] == second["occurrences"] == 26
    assert len(first["evidence"]) == 25 and len(second["evidence"]) == 1
    assert first["fingerprint"] == second["fingerprint"]
    assert len({e["id"] for e in first["evidence"] + second["evidence"]}) == 26


def test_equal_timestamp_latest_selection_matches_existing_analytics(signed_in, app, wav_bytes):
    call = complete(signed_in, app, wav_bytes)
    with app.state.db() as db:
        old = db.get(Evaluation, call["evaluation"]["id"])
        result = copy.deepcopy(old.result)
        result["categories"][0]["score"] = 0
        result["overall_score"] = 80
        db.add(
            Evaluation(
                id="zzzz-stable-tiebreak",
                call_id=call["id"],
                rubric_id=old.rubric_id,
                overall_score=80,
                result=result,
                rubric_version=old.rubric_version,
                provider="test",
                model="test",
                created_at=old.created_at,
                transcript_revision=0,
            )
        )
        db.commit()
    assert signed_in.get("/briefing").json()["signal_score"] == 80
    assert signed_in.get("/dashboard").json()["average_score"] == 80
    assert signed_in.get("/calls/" + call["id"]).json()["qa_score"] == 80
