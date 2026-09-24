import time
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import delete, select
from .auth import get_db, require
from .models import AdminEvent, Employee, EmployeeImport
from .services.employee_import import HEADERS, parse, validate
from .services.hierarchy import lock_organization, set_manager

router = APIRouter(prefix="/employee-imports")


@router.get("/template.csv")
def template(user=Depends(require("manage_employees"))):
    return Response(
        ",".join(HEADERS)
        + "\nAlex,Example,alex@example.com,EMP-001,,yes\nJamie,Example,jamie@example.com,EMP-002,EMP-001,no\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="signal-employees.csv"'},
    )


@router.post("/preview")
async def preview(file: UploadFile = File(...), user=Depends(require("manage_employees")), db=Depends(get_db)):
    content = await file.read(2_000_001)
    await file.close()
    if len(content) > 2_000_000:
        raise HTTPException(413, "Employee import must be at most 2 MB")
    rows = parse(content, file.filename or "")
    lock_organization(db, user.organization_id)
    db.execute(
        delete(EmployeeImport).where(EmployeeImport.expires_at < time.time(), EmployeeImport.committed_at.is_(None))
    )
    pending = db.scalars(
        select(EmployeeImport).where(EmployeeImport.actor_id == user.id, EmployeeImport.committed_at.is_(None))
    ).all()
    for old in pending:
        db.delete(old)
    result = validate(rows, db, user.organization_id)
    batch = EmployeeImport(
        organization_id=user.organization_id, actor_id=user.id, rows=rows, expires_at=time.time() + 1800
    )
    db.add(batch)
    db.commit()
    return {"id": batch.id, **result}


@router.post("/{batch_id}/commit")
def commit(batch_id: str, user=Depends(require("manage_employees")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    batch = db.scalar(
        select(EmployeeImport).where(
            EmployeeImport.id == batch_id,
            EmployeeImport.organization_id == user.organization_id,
            EmployeeImport.actor_id == user.id,
        )
    )
    if not batch:
        raise HTTPException(404, "Import not found")
    if batch.committed_at:
        return {"created": batch.count, "already_committed": True}
    if batch.expires_at <= time.time():
        raise HTTPException(409, "Preview expired. Upload the file again")
    result = validate(batch.rows, db, user.organization_id)
    if result["errors"]:
        raise HTTPException(
            409, "Import has errors or employees changed since preview. Upload a corrected file for a fresh preview."
        )
    created = []
    for row in result["rows"]:
        employee = Employee(
            organization_id=user.organization_id,
            name=row["name"],
            email=row["email"],
            external_id=row["external_id"],
            manager_eligible=row["manager_eligible"],
        )
        db.add(employee)
        db.flush()
        created.append(employee)
    for employee, row in zip(created, result["rows"]):
        key = row["manager_key"]
        if key:
            set_manager(db, employee, created[key[1]].id if key[0] == "new" else key[1], user)
    batch.committed_at = time.time()
    batch.count = len(created)
    batch.rows = []  # Minimize retained preview PII after commit; employees and hierarchy audit remain.
    db.add(
        AdminEvent(
            organization_id=user.organization_id,
            actor_id=user.id,
            resource_type="employee_import",
            resource_id=batch.id,
            action="created_" + str(len(created)),
        )
    )
    db.commit()
    return {"created": len(created), "already_committed": False}
