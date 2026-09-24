"""Current direct reporting, not role-based access or historical-as-of attribution."""

from fastapi import HTTPException
from sqlalchemy import select, update, or_
from ..models import Employee, EmployeeHierarchyChange, Organization, Call
from .performance import current_performance, evaluated_view


def employee_in_org(db, employee_id, organization_id):
    value = db.scalar(select(Employee).where(Employee.id == employee_id, Employee.organization_id == organization_id))
    if value is None:
        raise HTTPException(404, "Employee not found")
    return value


def lock_organization(db, organization_id):
    # Serializes cycle checks with every reporting/link/deactivation mutation.
    db.execute(update(Organization).where(Organization.id == organization_id).values(name=Organization.name))


def set_manager(db, employee, manager_id, actor):
    if manager_id == employee.manager_id:
        return
    if manager_id:
        manager = employee_in_org(db, manager_id, employee.organization_id)
        if not manager.manager_eligible:
            raise HTTPException(422, "Select an employee explicitly designated as a Manager.")
        if not manager.active:
            raise HTTPException(409, "Reactivate this manager before assigning new direct reports.")
        seen = {employee.id}
        while manager:
            if manager.id in seen:
                raise HTTPException(422, "Reporting relationships cannot contain a cycle or self-management.")
            seen.add(manager.id)
            manager = employee_in_org(db, manager.manager_id, employee.organization_id) if manager.manager_id else None
    db.add(
        EmployeeHierarchyChange(
            employee_id=employee.id,
            kind="manager",
            previous_manager_id=employee.manager_id,
            manager_id=manager_id,
            actor_id=actor.id,
        )
    )
    employee.manager_id = manager_id


def manager_filter(db, manager_id, organization_id):
    if manager_id != "unassigned":
        if not employee_in_org(db, manager_id, organization_id).manager_eligible:
            raise HTTPException(422, "Select a designated Manager.")
    reports = select(Employee.id).where(
        Employee.organization_id == organization_id,
        Employee.manager_id.is_(None) if manager_id == "unassigned" else Employee.manager_id == manager_id,
    )
    return (
        or_(Call.employee_id.is_(None), Call.employee_id.in_(reports))
        if manager_id == "unassigned"
        else Call.employee_id.in_(reports)
    )


def person(value):
    return {"id": value.id, "name": value.name, "active": value.active} if value else None


def team_performance(db, manager, include_details=True):
    reports = db.scalars(
        select(Employee)
        .where(Employee.organization_id == manager.organization_id, Employee.manager_id == manager.id)
        .order_by(Employee.name, Employee.id)
    ).all()
    calls = db.scalars(
        select(Call)
        .where(Call.organization_id == manager.organization_id, Call.employee_id.in_([e.id for e in reports]))
        .order_by(Call.created_at.desc(), Call.id)
    ).all()
    performance = current_performance(calls, db)
    result = {
        "manager": person(manager),
        "direct_reports": len(reports),
        "performance": performance,
        "requiring_review": sum(
            1 for c in calls if (v := evaluated_view(c, db)) and (v["stale"] or not v["reviewed_at"])
        ),
        "failed": sum(c.status == "failed" for c in calls),
    }
    if include_details:
        result["members"] = [
            {**person(e), "performance": current_performance([c for c in calls if c.employee_id == e.id], db)}
            for e in reports
        ]
        result["recent"] = [
            {
                "id": c.id,
                "filename": c.filename,
                "status": c.status,
                "employee_id": c.employee_id,
                "score": v["final_score"] if (v := evaluated_view(c, db)) and not v["stale"] else None,
            }
            for c in calls[:10]
        ]
    return result
