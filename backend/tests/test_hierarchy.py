import copy
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from app.models import User
from .test_employee_performance import correct
from .test_supervisor_controls import complete, other_tenant, supervisor


def employee(client, name):
    # Hierarchy tests explicitly create eligible reporting targets.
    return client.post("/employees", json={"name": name, "manager_eligible": True}).json()


def edit(client, value, manager_id=None, **changes):
    fresh = client.get("/employees/" + value["id"]).json()
    body = {k: fresh[k] for k in ("name", "title", "active", "revision")}
    return client.put("/employees/" + value["id"], json={**body, "manager_id": manager_id, **changes})


def team(client, person):
    result = client.get("/employees/" + person["id"] + "/team")
    assert result.status_code == 200, result.text
    return result.json()


def assign(client, call, person):
    fresh = client.get("/calls/" + call["id"]).json()
    response = client.post(
        "/calls/" + call["id"] + "/assignment",
        json={"employee_id": person["id"] if person else None, "revision": fresh["assignment_revision"]},
    )
    assert response.status_code == 200


def test_reporting_create_move_remove_and_audit(signed_in):
    sarah, david = employee(signed_in, "Sarah"), employee(signed_in, "David")
    result = signed_in.post("/employees", json={"name": "John", "manager_id": sarah["id"]})
    assert result.status_code == 201
    john = result.json()
    assert [e["id"] for e in signed_in.get("/employees?manager_id=" + sarah["id"]).json()["items"]] == [john["id"]]
    assert team(signed_in, sarah)["direct_reports"] == 1
    assert {e["id"] for e in signed_in.get("/employees?managers_only=true").json()["items"]} == {
        sarah["id"],
        david["id"],
    }
    assert edit(signed_in, john, david["id"]).status_code == 200
    assert team(signed_in, sarah)["direct_reports"] == 0
    assert team(signed_in, david)["direct_reports"] == 1
    assert edit(signed_in, john).status_code == 200
    history = signed_in.get("/employees/" + john["id"] + "/hierarchy").json()["history"]
    assert len(history) == 3
    assert history[0]["previous_manager"]["id"] == david["id"] and history[0]["manager"] is None
    assert history[1]["previous_manager"]["id"] == sarah["id"] and history[1]["manager"]["id"] == david["id"]
    assert history[0]["actor"]["name"] and history[0]["changed_at"]
    assert signed_in.get("/manager-teams").json()["total"] == 2


def test_self_direct_and_deep_cycles_rejected(signed_in):
    a, b, c = [employee(signed_in, n) for n in ["A", "B", "C"]]
    assert edit(signed_in, a, a["id"]).status_code == 422
    assert edit(signed_in, b, a["id"]).status_code == 200
    assert edit(signed_in, a, b["id"]).status_code == 422
    assert edit(signed_in, c, b["id"]).status_code == 200
    assert edit(signed_in, a, c["id"]).status_code == 422
    assert signed_in.get("/employees/" + a["id"] + "/hierarchy").json()["history"] == []


def test_concurrent_cycle_attempt_is_serialized(signed_in):
    a, b = employee(signed_in, "A"), employee(signed_in, "B")

    def put(pair):
        e, m = pair
        return signed_in.put(
            "/employees/" + e["id"], json={"name": e["name"], "revision": 1, "manager_id": m["id"]}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(put, [(a, b), (b, a)]))
    assert sorted(statuses) == [200, 422]


def test_inactive_manager_retains_reports_but_cannot_receive_new_reports(signed_in):
    manager, report, new = [employee(signed_in, n) for n in ["Manager", "Report", "New"]]
    assert edit(signed_in, report, manager["id"]).status_code == 200
    assert edit(signed_in, manager, active=False).status_code == 200
    assert team(signed_in, manager)["direct_reports"] == 1
    assert team(signed_in, manager)["manager"]["active"] is False
    assert edit(signed_in, report, manager["id"], title="Updated safely").status_code == 200
    assert edit(signed_in, new, manager["id"]).status_code == 409
    assert signed_in.get("/manager-teams").json()["items"][0]["manager"]["active"] is False
    assert edit(signed_in, report).status_code == 200
    assert len(signed_in.get("/employees/" + report["id"] + "/hierarchy").json()["history"]) == 2


def test_weighted_current_team_scores_filters_moves_and_history(signed_in, app, wav_bytes):
    sarah, david, a, b, c = [employee(signed_in, n) for n in ["Sarah", "David", "John", "Maria", "Robert"]]
    edit(signed_in, a, sarah["id"])
    edit(signed_in, b, sarah["id"])
    edit(signed_in, c, david["id"])
    calls = [complete(signed_in, app, wav_bytes) for _ in range(4)]
    for call, person in zip(calls, [a, a, b, sarah]):
        assign(signed_in, call, person)
    qa = calls[2]["evaluation"]
    assert (
        signed_in.post(
            f"/calls/{calls[2]['id']}/evaluations/{qa['id']}/categories/greeting",
            json={"score": 0, "reason": "Checked original evidence", "revision": qa["revision"]},
        ).status_code
        == 200
    )
    initial = team(signed_in, sarah)
    assert initial["performance"]["signal_score"] == 86.7  # (90 + 90 + 80)/3, not (90+80)/2
    assert initial["performance"]["analyzed"] == 3
    assert signed_in.get("/calls?manager_id=" + sarah["id"]).json()["total"] == 3
    assert signed_in.get("/calls?manager_id=" + sarah["id"] + "&employee_id=" + a["id"]).json()["total"] == 2
    assert signed_in.get("/calls?manager_id=" + sarah["id"] + "&employee_id=" + c["id"]).status_code == 422
    assert signed_in.get("/calls?manager_id=" + sarah["id"] + "&employee_id=unassigned").status_code == 422
    # Managers' own interactions are not part of their direct-report team; no-manager covers roots.
    assert signed_in.get("/calls?manager_id=unassigned").json()["total"] == 1
    correct(signed_in, calls[0])
    assert team(signed_in, sarah)["performance"]["signal_score"] == 85
    assert team(signed_in, sarah)["performance"]["stale"] == 1
    history = copy.deepcopy(signed_in.get("/calls/" + calls[2]["id"] + "/evaluations").json())
    assert edit(signed_in, b, david["id"]).status_code == 200
    assert team(signed_in, sarah)["performance"]["signal_score"] == 90
    assert team(signed_in, david)["performance"]["signal_score"] == 80
    assert signed_in.get("/calls/" + calls[2]["id"] + "/evaluations").json() == history
    assign(signed_in, calls[1], c)
    assert team(signed_in, sarah)["performance"]["signal_score"] is None
    assert team(signed_in, david)["performance"]["signal_score"] == 85
    # A replacement evaluation supersedes the adjusted historical result, never double counts.
    signed_in.post(
        "/calls/" + calls[2]["id"] + "/reevaluate", json={"rubric_id": qa["rubric_id"], "evaluation_id": qa["id"]}
    )
    app.state.processor.process(calls[2]["id"])
    assert team(signed_in, david)["performance"]["analyzed"] == 2
    assert team(signed_in, david)["performance"]["signal_score"] == 90
    assert len(signed_in.get("/calls/" + calls[2]["id"] + "/evaluations").json()) == 2
    assert signed_in.get("/manager-teams?sort=score").json()["items"][0]["manager"]["id"] == david["id"]


def test_tenant_id_manipulation_rejected(signed_in, app, wav_bytes):
    a = employee(signed_in, "Private manager")
    with app.state.db() as db:
        owner_id = db.scalar(select(User.id).where(User.email == "admin@example.test"))
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    b = employee(signed_in, "Other person")
    assert edit(signed_in, b, a["id"]).status_code == 404
    assert signed_in.post("/employees", json={"name": "Forged", "manager_id": a["id"]}).status_code == 404
    for path in ["/calls?manager_id=", "/employees?manager_id="]:
        assert signed_in.get(path + a["id"]).status_code == 404
    for path in ["/team", "/hierarchy"]:
        assert signed_in.get("/employees/" + a["id"] + path).status_code == 404
    assert signed_in.get("/manager-teams").json()["total"] == 1
    assert (
        signed_in.put("/employees/" + b["id"] + "/user-link", json={"user_id": owner_id, "revision": 1}).status_code
        == 404
    )
    assert (
        signed_in.put("/employees/" + a["id"] + "/user-link", json={"user_id": None, "revision": 1}).status_code == 404
    )


def test_optional_account_link_unique_audited_and_permissions_unchanged(signed_in, app):
    a, b = employee(signed_in, "Manager"), employee(signed_in, "Other employee")
    with app.state.db() as db:
        u = db.scalar(select(User).where(User.email == "admin@example.test"))
        uid = u.id
        role = u.role
    endpoint = "/employees/" + a["id"] + "/user-link"
    assert signed_in.put(endpoint, json={"user_id": uid, "revision": 1}).status_code == 200
    assert (
        signed_in.put("/employees/" + b["id"] + "/user-link", json={"user_id": uid, "revision": 1}).status_code == 409
    )
    assert signed_in.put(endpoint, json={"user_id": None, "revision": 1}).status_code == 409
    assert signed_in.put(endpoint, json={"user_id": None, "revision": 2}).status_code == 200
    assert len(signed_in.get("/employees/" + a["id"] + "/hierarchy").json()["history"]) == 2
    with app.state.db() as db:
        assert db.get(User, uid).role == role
    supervisor(signed_in)
    assert signed_in.put(endpoint, json={"user_id": uid, "revision": 3}).status_code == 403
    assert edit(signed_in, b, a["id"]).status_code == 403
    assert signed_in.get("/manager-teams").status_code == 200


def test_old_employee_edit_does_not_clear_manager_and_scoped_access_is_not_enabled(signed_in, app):
    manager, report = employee(signed_in, "Manager"), employee(signed_in, "Report")
    edited = edit(signed_in, report, manager["id"]).json()
    assert (
        signed_in.put("/employees/" + report["id"], json={"name": "Rename", "revision": edited["revision"]}).status_code
        == 200
    )
    assert signed_in.get("/employees/" + report["id"]).json()["manager_id"] == manager["id"]
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.role = "MANAGER"
        db.commit()
    assert edit(signed_in, report).status_code == 200
    assert signed_in.get("/employees").json()["total"] == 2
    assert (
        signed_in.put("/employees/" + manager["id"] + "/user-link", json={"user_id": None, "revision": 1}).status_code
        == 403
    )
