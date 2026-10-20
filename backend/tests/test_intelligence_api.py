from tests.test_call_attributes import stored_call
from app.models import Call, Organization, CallAttribute, AttributeEvent, User, Role, RelatedExclusion
from sqlalchemy import select


def test_edit_search_removal_and_revision(app, signed_in):
    call = stored_call(app)
    base = f"/calls/{call}"
    assert signed_in.post(base + "/intelligence/refresh").status_code == 200
    values = signed_in.get(base + "/intelligence").json()["attributes"]
    order = next(v for v in values if v["key"] == "order")
    assert order["value"] == "104582" and not order["verified"]
    response = signed_in.put(
        base + "/attributes/order", json={"value": "AB-104582", "revision": order["revision"], "verified": True}
    )
    assert response.status_code == 200, response.text
    assert response.json()["verified"]
    assert signed_in.get("/intelligence/search", params={"q": "ab104582", "key": "order"}).json()["total"] == 1
    assert signed_in.get("/intelligence/search", params={"q": "10458", "key": "order"}).json()["total"] == 0
    assert signed_in.get("/intelligence/search", params={"q": "smith", "key": "customer"}).json()["total"] == 1
    assert signed_in.get("/intelligence/search", params={"q": "Main Street", "key": "address"}).json()["total"] == 1
    assert (
        signed_in.put(base + "/attributes/order", json={"value": "12345", "revision": order["revision"]}).status_code
        == 409
    )
    assert (
        signed_in.put(
            base + "/attributes/order", json={"value": None, "revision": response.json()["revision"]}
        ).status_code
        == 200
    )
    signed_in.post(base + "/intelligence/refresh")
    assert signed_in.get("/intelligence/search", params={"q": "104582"}).json()["total"] == 0
    assert signed_in.get(base + "/attributes/history?limit=1").json()["total"] == 6


def test_tenant_boundary_and_vocabulary(app, signed_in):
    call = stored_call(app)
    with app.state.db() as db:
        org = Organization(name="Other tenant")
        db.add(org)
        db.flush()
        db.get(Call, call).organization_id = org.id
        db.commit()
    for suffix in ["/intelligence", "/attributes/history", "/related"][:2]:
        assert signed_in.get(f"/calls/{call}" + suffix).status_code == 404
    assert signed_in.post(f"/calls/{call}/intelligence/refresh").status_code == 404
    assert signed_in.put(f"/calls/{call}/attributes/order", json={"value": "12345", "revision": 0}).status_code == 404
    assert signed_in.get("/intelligence/search?q=12345").json()["total"] == 0
    response = signed_in.put("/organization/transcription-vocabulary", json={"alternate_names": ["Test Logistics"]})
    assert response.status_code == 200, response.text
    assert response.json()["registered_name"] == "Test workspace"
    signed_in.post("/auth/logout")
    signed_in.post("/auth/login", json={"email": "supervisor@example.test", "password": "test-password-only"})
    assert signed_in.put("/organization/transcription-vocabulary", json={}).status_code == 403


def test_related_requires_both_verified_and_exclusion_is_bidirectional(app, signed_in):
    first, second = stored_call(app), stored_call(app)
    for call in [first, second]:
        signed_in.post(f"/calls/{call}/intelligence/refresh")
    assert signed_in.get(f"/calls/{first}/related").json()["total"] == 0
    for call in [first, second]:
        values = signed_in.get(f"/calls/{call}/intelligence").json()["attributes"]
        order = next(v for v in values if v["key"] == "order")
        assert (
            signed_in.put(
                f"/calls/{call}/attributes/order", json={"value": order["value"], "revision": order["revision"]}
            ).status_code
            == 200
        )
    result = signed_in.get(f"/calls/{first}/related").json()
    assert result["total"] == 1 and result["items"][0]["id"] == second
    assert result["items"][0]["matches"][0]["key"] == "order"
    assert signed_in.post(f"/calls/{first}/related/{second}/exclude").status_code == 200
    for call in [first, second]:
        signed_in.post(f"/calls/{call}/intelligence/refresh")
        assert signed_in.get(f"/calls/{call}/related").json()["total"] == 0


def test_search_pagination_hawb_and_full_tenant_permissions(app, signed_in):
    local, foreign = stored_call(app), stored_call(app)
    for call in [local, foreign]:
        signed_in.post(f"/calls/{call}/intelligence/refresh")
        fields = signed_in.get(f"/calls/{call}/intelligence").json()["attributes"]
        for field in fields:
            if field["key"] in {"order", "hawb"}:
                signed_in.put(
                    f"/calls/{call}/attributes/{field['key']}",
                    json={"value": field["value"], "revision": field["revision"]},
                )
    assert signed_in.get("/intelligence/search?q=123456789&key=hawb&limit=1").json()["total"] == 2
    first = signed_in.get("/intelligence/search?q=smith&key=customer&limit=1").json()["items"][0]["id"]
    second = signed_in.get("/intelligence/search?q=smith&key=customer&limit=1&offset=1").json()["items"][0]["id"]
    assert first != second
    with app.state.db() as db:
        org = Organization(name="Unrelated company")
        db.add(org)
        db.flush()
        call = db.get(Call, foreign)
        call.organization_id = org.id
        for model in [CallAttribute, AttributeEvent]:
            for row in db.scalars(select(model).where(model.call_id == foreign)):
                row.organization_id = org.id
        db.commit()
    assert signed_in.get("/intelligence/search?q=123456789&key=hawb").json()["total"] == 1
    assert signed_in.get(f"/calls/{local}/related").json()["total"] == 0
    assert signed_in.get(f"/calls/{foreign}/related").status_code == 404
    assert signed_in.post(f"/calls/{local}/related/{foreign}/exclude").status_code == 404
    assert signed_in.get(f"/calls/{foreign}/attributes/history").status_code == 404
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.role = Role.EMPLOYEE
        db.commit()
    assert signed_in.get("/intelligence/search?q=123456789").status_code == 403
    assert signed_in.get(f"/calls/{local}/intelligence").status_code == 403
    signed_in.post("/auth/logout")
    assert signed_in.get("/intelligence/search?q=123456789").status_code == 401


def test_hawb_only_relationship_and_deletion_cleanup(app, signed_in):
    first = stored_call(app)
    second = stored_call(app, "Order 999999. HAWB 123456789.")
    different = stored_call(app, "Order 777777. HAWB 999999999.")
    for call in [first, second, different]:
        signed_in.post(f"/calls/{call}/intelligence/refresh")
        values = signed_in.get(f"/calls/{call}/intelligence").json()["attributes"]
        for row in values:
            if row["key"] in {"hawb", "order"}:
                assert (
                    signed_in.put(
                        f"/calls/{call}/attributes/{row['key']}",
                        json={"value": row["value"], "revision": row["revision"]},
                    ).status_code
                    == 200
                )
    related = signed_in.get(f"/calls/{first}/related").json()
    assert related["total"] == 1 and related["items"][0]["id"] == second
    assert [m["key"] for m in related["items"][0]["matches"]] == ["hawb"]
    signed_in.post(f"/calls/{first}/related/{second}/exclude")
    assert signed_in.delete(f"/calls/{first}").status_code == 200
    with app.state.db() as db:
        for model in [CallAttribute, AttributeEvent]:
            assert not db.scalars(select(model).where(model.call_id == first)).all()
        assert not db.scalars(select(RelatedExclusion)).all()
