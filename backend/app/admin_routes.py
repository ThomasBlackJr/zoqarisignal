"""Tenant-scoped destructive controls; retained audit contains no deleted content."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete, update, func, or_
from .auth import get_db, require
from .models import (
    Call,
    Employee,
    EmployeeAssignment,
    EmployeeHierarchyChange,
    Evaluation,
    Transcript,
    ScoreAdjustment,
    SpeakerCorrection,
    UploadItem,
    AdminEvent,
    PendingAudioDeletion,
    Status,
)
from .review_routes import lock_call
from .review_schemas import Revision
from .services.hierarchy import lock_organization, employee_in_org
from .services.deletion import cleanup_audio

router = APIRouter()


@router.delete("/calls/{call_id}")
def delete_call(call_id: str, request: Request, user=Depends(require("delete_records")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    call = db.scalar(select(Call).where(Call.id == call_id, Call.organization_id == user.organization_id))
    if call is None:
        prior = db.scalar(
            select(AdminEvent).where(
                AdminEvent.resource_id == call_id,
                AdminEvent.resource_type == "call",
                AdminEvent.organization_id == user.organization_id,
                AdminEvent.action.in_(["deleted", "audio_deletion_pending"]),
            )
        )
        if prior is None:
            raise HTTPException(404, "Interaction not found")
        db.rollback()
    else:
        call = lock_call(db, call_id, user)
        if call.status in {Status.TRANSCRIBING, Status.ANALYZING}:
            raise HTTPException(409, "Wait for processing to finish before deleting this interaction.")
        audit = AdminEvent(
            organization_id=user.organization_id,
            actor_id=user.id,
            resource_type="call",
            resource_id=call.id,
            action="audio_deletion_pending",
        )
        db.add(audit)
        db.flush()
        db.add(
            PendingAudioDeletion(
                call_id=call.id, organization_id=user.organization_id, storage_name=call.storage_name, event_id=audit.id
            )
        )
        # Tombstones cannot be uploaded into again; the historical manifest remains readable.
        db.execute(
            update(UploadItem)
            .where(UploadItem.call_id == call.id)
            .values(call_id=None, filename="Deleted interaction", size_bytes=0, status="deleted", error=None)
        )
        evaluation_ids = select(Evaluation.id).where(Evaluation.call_id == call.id)
        db.execute(delete(ScoreAdjustment).where(ScoreAdjustment.evaluation_id.in_(evaluation_ids)))
        for model in (SpeakerCorrection, EmployeeAssignment, Evaluation, Transcript):
            db.execute(delete(model).where(model.call_id == call.id))
        db.execute(delete(Call).where(Call.id == call.id))
        db.commit()
    complete = cleanup_audio(request.app.state.db, request.app.state.settings, call_id)
    return {
        "status": "deleted" if complete else "audio_deletion_pending",
        "message": "Interaction deleted."
        if complete
        else "Signal data removed. Recording deletion is pending; the server will retry cleanup. The recording is no longer accessible in Signal.",
    }


@router.post("/employees/{employee_id}/archive")
def archive_employee(employee_id: str, body: Revision, user=Depends(require("delete_records")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    employee = employee_in_org(db, employee_id, user.organization_id)
    if employee.revision != body.revision:
        raise HTTPException(409, "Employee changed. Reload before archiving.")
    if employee.active:
        employee.active = False
        employee.revision += 1
        db.add(
            AdminEvent(
                organization_id=user.organization_id,
                actor_id=user.id,
                resource_type="employee",
                resource_id=employee.id,
                action="archived",
            )
        )
        db.commit()
    return {"status": "archived", "revision": employee.revision}


@router.delete("/employees/{employee_id}")
def delete_employee(employee_id: str, body: Revision, user=Depends(require("delete_records")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    employee = employee_in_org(db, employee_id, user.organization_id)
    if employee.revision != body.revision:
        raise HTTPException(409, "Employee changed. Reload before deleting.")

    def count(model, predicate):
        return db.scalar(select(func.count()).select_from(model).where(predicate))

    references = {
        "interactions": count(Call, Call.employee_id == employee.id),
        "assignment-history records": count(
            EmployeeAssignment,
            or_(EmployeeAssignment.employee_id == employee.id, EmployeeAssignment.previous_employee_id == employee.id),
        ),
        "direct reports": count(Employee, Employee.manager_id == employee.id),
        "reporting/link-history records": count(
            EmployeeHierarchyChange,
            or_(
                EmployeeHierarchyChange.employee_id == employee.id,
                EmployeeHierarchyChange.manager_id == employee.id,
                EmployeeHierarchyChange.previous_manager_id == employee.id,
            ),
        ),
        "linked login accounts": int(employee.linked_user_id is not None),
        "current manager relationships": int(employee.manager_id is not None),
    }
    if any(references.values()):
        detail = ", ".join(f"{n} {label}" for label, n in references.items() if n)
        raise HTTPException(409, f"Permanent deletion blocked: {detail}. Archive this employee to preserve history.")
    db.add(
        AdminEvent(
            organization_id=user.organization_id,
            actor_id=user.id,
            resource_type="employee",
            resource_id=employee.id,
            action="deleted",
        )
    )
    db.delete(employee)
    db.commit()
    return {"status": "deleted"}


@router.get("/admin/events")
def events(user=Depends(require("delete_records")), db=Depends(get_db)):
    return [
        {
            "id": e.id,
            "actor_id": e.actor_id,
            "organization_id": e.organization_id,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "action": e.action,
            "created_at": e.created_at,
        }
        for e in db.scalars(
            select(AdminEvent)
            .where(AdminEvent.organization_id == user.organization_id)
            .order_by(AdminEvent.created_at.desc(), AdminEvent.id)
            .limit(100)
        )
    ]
