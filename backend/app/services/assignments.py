"""Shared tenant-safe operator validation and append-only assignment."""

from fastapi import HTTPException
from ..auth import PERMISSIONS
from ..models import EmployeeAssignment
from .hierarchy import employee_in_org


def selected_employee(db, user, employee_id):
    if employee_id is None:
        return None
    if "assign_interactions" not in PERMISSIONS.get(user.role, set()):
        raise HTTPException(403, "Your role does not permit operator assignment")
    employee = employee_in_org(db, employee_id, user.organization_id)
    if not employee.active:
        raise HTTPException(409, "Reactivate this employee before assigning new interactions.")
    return employee


def assign_employee(db, call, employee_id, user):
    if call.employee_id != employee_id:
        db.add(
            EmployeeAssignment(
                call_id=call.id, previous_employee_id=call.employee_id, employee_id=employee_id, changed_by=user.id
            )
        )
        call.employee_id = employee_id
        call.assignment_revision = (call.assignment_revision or 0) + 1
