"""Tracked employees are independent of login accounts. Assignment is a separate audit."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator
from sqlalchemy import select, func
from .auth import get_db, require
from .models import Call, Employee, EmployeeAssignment, AdminEvent
from .schemas import StrictModel
from .review_routes import lock_call
from .services.hierarchy import employee_in_org, lock_organization, set_manager
from .services.performance import current_performance, evaluated_view

router = APIRouter()


class EmployeeBody(StrictModel):
    manager_eligible: bool = False
    manager_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=120)
    active: bool = True
    revision: int = Field(default=1, ge=1, strict=True)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Employee name is required")
        return value.strip()


class Assignment(StrictModel):
    employee_id: str | None
    revision: int = Field(ge=0, strict=True)


def employee_view(value):
    return {
        "id": value.id,
        "name": value.name,
        "email": value.email,
        "external_id": value.external_id,
        "title": value.title,
        "active": value.active,
        "revision": value.revision,
        "manager_id": value.manager_id,
        "manager_eligible": value.manager_eligible,
    }


def get_employee(db, employee_id, user):
    return employee_in_org(db, employee_id, user.organization_id)


@router.get("/employees")
def employees(
    q: str = Query("", max_length=120),
    active: bool | None = None,
    manager_id: str | None = None,
    managers_only: bool = False,
    offset: int = Query(0, ge=0),
    user=Depends(require("review")),
    db=Depends(get_db),
):
    query = select(Employee).where(Employee.organization_id == user.organization_id)
    if manager_id:
        if manager_id != "unassigned":
            get_employee(db, manager_id, user)
        query = query.where(
            Employee.manager_id.is_(None) if manager_id == "unassigned" else Employee.manager_id == manager_id
        )
    if managers_only:
        query = query.where(Employee.manager_eligible.is_(True))
    if q.strip():
        query = query.where(Employee.name.icontains(q.strip(), autoescape=True))
    if active is not None:
        query = query.where(Employee.active == active)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {
        "total": total,
        "items": [
            employee_view(e) for e in db.scalars(query.order_by(Employee.name, Employee.id).offset(offset).limit(100))
        ],
    }


@router.post("/employees", status_code=201)
def create(body: EmployeeBody, user=Depends(require("manage_employees")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    employee = Employee(
        organization_id=user.organization_id,
        name=body.name,
        title=body.title,
        active=body.active,
        manager_eligible=body.manager_eligible,
    )
    db.add(employee)
    db.flush()
    set_manager(db, employee, body.manager_id, user)
    db.commit()
    return employee_view(employee)


@router.put("/employees/{employee_id}")
def edit(employee_id: str, body: EmployeeBody, user=Depends(require("manage_employees")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    employee = get_employee(db, employee_id, user)
    if employee.revision != body.revision:
        raise HTTPException(409, "Employee changed. Reload before saving.")
    if "manager_id" in body.model_fields_set:
        set_manager(db, employee, body.manager_id, user)
    if "manager_eligible" in body.model_fields_set and body.manager_eligible != employee.manager_eligible:
        count = db.scalar(select(func.count()).select_from(Employee).where(Employee.manager_id == employee.id))
        if not body.manager_eligible and count:
            raise HTTPException(
                409,
                f"This manager has {count} direct reports. Reassign or remove them before removing Manager designation.",
            )
        employee.manager_eligible = body.manager_eligible
        db.add(
            AdminEvent(
                organization_id=user.organization_id,
                actor_id=user.id,
                resource_type="employee",
                resource_id=employee.id,
                action="manager_designated" if body.manager_eligible else "manager_removed",
            )
        )
    if body.active != employee.active:
        db.add(
            AdminEvent(
                organization_id=user.organization_id,
                actor_id=user.id,
                resource_type="employee",
                resource_id=employee.id,
                action="restored" if body.active else "archived",
            )
        )
    employee.name, employee.title, employee.active = body.name, body.title, body.active
    employee.revision += 1
    db.commit()
    return employee_view(employee)


@router.get("/employees/{employee_id}")
def profile(employee_id: str, user=Depends(require("review")), db=Depends(get_db)):
    employee = get_employee(db, employee_id, user)
    calls = db.scalars(
        select(Call)
        .where(Call.organization_id == user.organization_id, Call.employee_id == employee.id)
        .order_by(Call.created_at.desc())
    ).all()
    return {
        **employee_view(employee),
        "performance": current_performance(calls, db),
        "recent": [
            {
                "id": c.id,
                "filename": c.filename,
                "created_at": c.created_at,
                "status": c.status,
                "score": v["final_score"] if (v := evaluated_view(c, db)) and not v["stale"] else None,
            }
            for c in calls[:10]
        ],
    }


@router.post("/calls/{call_id}/assignment")
def assign(call_id: str, body: Assignment, user=Depends(require("assign_interactions")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    call = lock_call(db, call_id, user)
    if call.assignment_revision != body.revision:
        raise HTTPException(409, "Assignment changed. Reload before saving.")
    if body.employee_id:
        employee = get_employee(db, body.employee_id, user)
        if not employee.active:
            raise HTTPException(409, "Reactivate this employee before assigning new interactions.")
    if call.employee_id != body.employee_id:
        db.add(
            EmployeeAssignment(
                call_id=call.id, previous_employee_id=call.employee_id, employee_id=body.employee_id, changed_by=user.id
            )
        )
        call.employee_id = body.employee_id
        call.assignment_revision += 1
        db.commit()
    return {"employee_id": call.employee_id, "revision": call.assignment_revision}


@router.get("/calls/{call_id}/assignments")
def assignment_history(call_id: str, user=Depends(require("review")), db=Depends(get_db)):
    if db.scalar(select(Call.id).where(Call.id == call_id, Call.organization_id == user.organization_id)) is None:
        raise HTTPException(404, "Call not found")
    return [
        {
            "id": a.id,
            "previous_employee": a.previous_employee.name if a.previous_employee else None,
            "employee": a.employee.name if a.employee else None,
            "actor": a.actor.name,
            "changed_at": a.changed_at,
        }
        for a in db.scalars(
            select(EmployeeAssignment)
            .where(EmployeeAssignment.call_id == call_id)
            .order_by(EmployeeAssignment.id.desc())
        )
    ]
