from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select
from .auth import get_db, require
from .models import Employee, EmployeeHierarchyChange, User
from .schemas import StrictModel
from .services.hierarchy import employee_in_org, lock_organization, person, team_performance

router = APIRouter()


class UserLink(StrictModel):
    user_id: str | None = Field(min_length=1, max_length=36)
    revision: int = Field(ge=1, strict=True)


@router.get("/manager-teams")
def teams(
    q: str = Query("", max_length=120),
    sort: Literal["name", "score", "interactions"] = "name",
    offset: int = Query(0, ge=0),
    user=Depends(require("review")),
    db=Depends(get_db),
):
    rows = db.scalars(
        select(Employee).where(
            Employee.organization_id == user.organization_id,
            Employee.name.icontains(q.strip(), autoescape=True),
            Employee.manager_eligible.is_(True),
        )
    ).all()
    values = [team_performance(db, e, include_details=False) for e in rows]
    if sort == "name":
        values.sort(key=lambda v: (v["manager"]["name"].casefold(), v["manager"]["id"]))
    else:
        key = "signal_score" if sort == "score" else "interactions"
        values.sort(
            key=lambda v: (
                -(v["performance"][key] if v["performance"][key] is not None else -1),
                v["manager"]["name"].casefold(),
                v["manager"]["id"],
            )
        )
    return {"total": len(values), "items": values[offset : offset + 50]}


@router.get("/employees/{employee_id}/team")
def team(employee_id: str, user=Depends(require("review")), db=Depends(get_db)):
    employee = employee_in_org(db, employee_id, user.organization_id)
    if not employee.manager_eligible:
        raise HTTPException(422, "This employee is not designated as a Manager.")
    return team_performance(db, employee)


@router.get("/employees/{employee_id}/hierarchy")
def hierarchy(employee_id: str, user=Depends(require("review")), db=Depends(get_db)):
    employee = employee_in_org(db, employee_id, user.organization_id)
    manager = employee_in_org(db, employee.manager_id, user.organization_id) if employee.manager_id else None
    reports = db.scalars(
        select(Employee)
        .where(Employee.organization_id == user.organization_id, Employee.manager_id == employee.id)
        .order_by(Employee.name, Employee.id)
    ).all()
    linked = (
        db.scalar(select(User).where(User.id == employee.linked_user_id, User.organization_id == user.organization_id))
        if employee.linked_user_id
        else None
    )

    def label(model, key):
        v = (
            db.scalar(select(model).where(model.id == key, model.organization_id == user.organization_id))
            if key
            else None
        )
        return person(v)

    history = [
        {
            "id": a.id,
            "kind": a.kind,
            "previous_manager": label(Employee, a.previous_manager_id),
            "manager": label(Employee, a.manager_id),
            "previous_user": label(User, a.previous_user_id),
            "user": label(User, a.user_id),
            "actor": label(User, a.actor_id),
            "changed_at": a.changed_at,
        }
        for a in db.scalars(
            select(EmployeeHierarchyChange)
            .where(EmployeeHierarchyChange.employee_id == employee.id)
            .order_by(EmployeeHierarchyChange.id.desc())
        )
    ]
    return {
        "employee": person(employee),
        "revision": employee.revision,
        "manager": person(manager),
        "linked_user": person(linked),
        "direct_reports": [person(e) for e in reports],
        "history": history,
    }


@router.put("/employees/{employee_id}/user-link")
def link(employee_id: str, body: UserLink, user=Depends(require("manage_users")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    employee = employee_in_org(db, employee_id, user.organization_id)
    if body.revision != employee.revision:
        raise HTTPException(409, "Employee changed. Reload before linking.")
    if body.user_id:
        target = db.scalar(select(User).where(User.id == body.user_id, User.organization_id == user.organization_id))
        if target is None:
            raise HTTPException(404, "User not found")
        if body.user_id != employee.linked_user_id:
            if not target.active or not employee.active:
                raise HTTPException(409, "Activate the employee and user before creating a new link.")
            if db.scalar(select(Employee.id).where(Employee.linked_user_id == target.id, Employee.id != employee.id)):
                raise HTTPException(409, "This user is already linked to an employee. Unlink it there first.")
    if employee.linked_user_id != body.user_id:
        db.add(
            EmployeeHierarchyChange(
                employee_id=employee.id,
                kind="user_link",
                previous_user_id=employee.linked_user_id,
                user_id=body.user_id,
                actor_id=user.id,
            )
        )
        employee.linked_user_id = body.user_id
        employee.revision += 1
        db.commit()
    return {"user_id": employee.linked_user_id, "revision": employee.revision}
