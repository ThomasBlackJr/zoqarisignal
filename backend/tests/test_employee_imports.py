import io
from openpyxl import Workbook
from sqlalchemy import select, func
from app.models import Employee, User, AdminEvent, EmployeeImport, LEGACY_ORG

HEADER = "First Name,Last Name,Email,Employee ID,Manager,Manager Eligible\n"


def preview(client, rows):
    return client.post("/employee-imports/preview", files={"file": ("staff.csv", (HEADER + rows).encode(), "text/csv")})


def test_import_preview_two_pass_idempotent_no_accounts(signed_in, app):
    with app.state.db() as db:
        users = db.scalar(select(func.count()).select_from(User))
    result = preview(signed_in, "Jamie,Example,jamie@example.test,E2,E1,no\nAlex,Example,alex@example.test,E1,,yes\n")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["ready"] == 2 and body["errors"] == 0
    with app.state.db() as db:
        assert db.scalar(select(func.count()).select_from(Employee)) == 0
    assert signed_in.post(f"/employee-imports/{body['id']}/commit").json()["created"] == 2
    assert signed_in.post(f"/employee-imports/{body['id']}/commit").json()["already_committed"]
    with app.state.db() as db:
        assert db.scalar(select(func.count()).select_from(User)) == users
        people = {e.external_id: e for e in db.scalars(select(Employee))}
        assert people["e2"].manager_id == people["e1"].id
        assert db.scalar(select(AdminEvent).where(AdminEvent.resource_id == body["id"])).action == "created_2"
        assert db.get(EmployeeImport, body["id"]).rows == []


def test_row_errors_cycles_duplicates_and_no_partial_commit(signed_in):
    body = preview(signed_in, "A,One,bad,E1,E2,yes\nB,Two,,E2,E1,yes\nC,Three,,E1,missing,maybe\n").json()
    assert body["errors"] == 3
    assert "Duplicate" in str(body) and "Invalid email" in str(body)
    assert signed_in.post(f"/employee-imports/{body['id']}/commit").status_code == 409
    assert signed_in.get("/employees").json()["total"] == 0
    cycle = preview(signed_in, "A,One,,E1,E2,yes\nB,Two,,E2,E1,yes\n").json()
    assert cycle["errors"] == 2 and "cycle" in str(cycle)


def test_xlsx_and_formula_rejection(signed_in):
    wb = Workbook()
    wb.active.append(["First Name", "Last Name", "Employee ID"])
    wb.active.append(["Alex", "Example", "EMP1"])
    file = io.BytesIO()
    wb.save(file)
    result = signed_in.post("/employee-imports/preview", files={"file": ("staff.xlsx", file.getvalue())})
    assert result.status_code == 200 and result.json()["ready"] == 1
    wb.active["A2"] = "=WEBSERVICE(1)"
    file = io.BytesIO()
    wb.save(file)
    assert (
        signed_in.post("/employee-imports/preview", files={"file": ("staff.xlsx", file.getvalue())}).status_code == 422
    )


def test_revalidate_changed_directory_and_tenant_ownership(signed_in, app):
    from tests.test_flags import other_tenant

    body = preview(signed_in, "Alex,Example,,EMP1,,no\n").json()
    with app.state.db() as db:
        db.add(Employee(organization_id=LEGACY_ORG, name="Concurrent", external_id="emp1"))
        db.commit()
    assert signed_in.post(f"/employee-imports/{body['id']}/commit").status_code == 409
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.post(f"/employee-imports/{body['id']}/commit").status_code == 404
    own = preview(signed_in, "Alex,Example,,EMP1,,no\n").json()
    assert own["errors"] == 0


def test_expired_preview_permission_and_template(signed_in, app):
    assert "First Name" in signed_in.get("/employee-imports/template.csv").text
    body = preview(signed_in, "Alex,Example,,,,no\n").json()
    with app.state.db() as db:
        db.get(EmployeeImport, body["id"]).expires_at = 1
        db.commit()
    assert signed_in.post(f"/employee-imports/{body['id']}/commit").status_code == 409
    signed_in.post("/auth/login", json={"email": "supervisor@example.test", "password": "test-password-only"})
    assert preview(signed_in, "Alex,Example,,,,no\n").status_code == 403
