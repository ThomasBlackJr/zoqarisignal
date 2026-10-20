"""Audited account changes without credential disclosure, history deletion or implicit ownership."""

import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator, model_validator
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError

from .account_schemas import Email, OrganizationCreate
from .account_routes import send_token, limit
from .auth import PERMISSIONS, get_db, hasher, user_view
from .models import (
    User,
    Session,
    AccountToken,
    VerificationCode,
    Invitation,
    Employee,
    EmployeeHierarchyChange,
    PlatformEvent,
)
from .platform_routes import platform_admin, audit, Reason, organization, events
from .services.account_audit import account_event
from .services.verification import issue_code
from .services.entitlements import operational_access
from .services.hierarchy import set_manager
from .logging import event

router = APIRouter(prefix="/platform", tags=["platform users"])


class Confirm(Reason):
    confirmed: bool = Field(strict=True)

    @field_validator("confirmed")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation is required")
        return value


class Mutation(Confirm):
    revision: int = Field(ge=0, strict=True)


class Profile(Mutation):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def name(self):
        self.first_name, self.last_name = self.first_name.strip(), self.last_name.strip()
        if not self.first_name or len((self.first_name + " " + self.last_name).strip()) > 100:
            raise ValueError("A first name and a combined name of at most 100 characters are required")
        return self


class Create(Profile, Email):
    revision: int = Field(default=0, ge=0, strict=True)


class ChangeEmail(Mutation, Email):
    pass


class AccountStatus(Mutation):
    active: bool = Field(strict=True)


class Membership(Mutation):
    organization_id: str | None = Field(default=None, min_length=1, max_length=36)
    role: Literal["ADMIN", "MANAGER", "REVIEWER", "EMPLOYEE", "SUPERVISOR"] = "EMPLOYEE"


class EmployeeLink(Mutation):
    employee_id: str | None = Field(default=None, min_length=1, max_length=36)


class Manager(Mutation):
    manager_id: str | None = Field(default=None, min_length=1, max_length=36)
    employee_revision: int = Field(ge=1, strict=True)


class OwnerTransfer(Confirm):
    current_owner_id: str = Field(min_length=1, max_length=36)
    new_owner_id: str = Field(min_length=1, max_length=36)


class OrganizationEdit(Confirm, OrganizationCreate):
    pass


@router.put("/organizations/{organization_id}/profile")
def organization_profile(
    organization_id: str, body: OrganizationEdit, request: Request, actor=Depends(platform_admin), db=Depends(get_db)
):
    value = organization(db, organization_id, lock=True)
    old = value.name
    value.name = body.name
    audit(db, actor, "organization.updated", value.id, body.reason, {"old_name": old, "new_name": value.name})
    db.commit()
    return {"id": value.id, "name": value.name}


@router.get("/organizations/{organization_id}/ownership")
def ownership(organization_id: str, q: str = "", actor=Depends(platform_admin), db=Depends(get_db)):
    organization(db, organization_id)
    owners = db.scalars(select(User).where(User.organization_id == organization_id, User.role == "OWNER")).all()
    candidates = db.scalars(
        select(User)
        .where(
            User.organization_id == organization_id,
            User.role != "OWNER",
            User.active.is_(True),
            User.email_verified.is_(True),
            User.name.icontains(q[:120].strip(), autoescape=True),
        )
        .order_by(User.name, User.id)
        .limit(50)
    ).all()
    result = {"owners": [user_view(u) for u in owners], "candidates": [user_view(u) for u in candidates]}
    audit(db, actor, "ownership.view", organization_id)
    db.commit()
    return result


def target(db, user_id):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


def locked_target(db, user_id, body, new_org=None):
    user = target(db, user_id)
    original = user.organization_id
    for org in sorted({v for v in (original, new_org) if v}):
        organization(db, org, lock=True)
    db.execute(update(User).where(User.id == user_id).values(active=User.active))
    db.refresh(user)
    if user.organization_id != original or user.admin_revision != body.revision:
        raise HTTPException(409, "User changed. Reload the account before trying again.")
    return user


def invalidate(db, user, invitations=False):
    db.execute(delete(Session).where(Session.user_id == user.id))
    db.execute(delete(AccountToken).where(AccountToken.user_id == user.id))
    db.execute(delete(VerificationCode).where(VerificationCode.user_id == user.id))
    if invitations:
        db.execute(
            update(Invitation)
            .where(Invitation.invited_by == user.id, Invitation.status == "pending")
            .values(status="revoked")
        )


def record(db, actor, user, action, reason, details=None):
    user.admin_revision += 1
    user.updated_at = time.time()
    audit(db, actor, action, user.organization_id, reason, {"user_id": user.id, **(details or {})})


def notify(request, email, text):
    try:
        request.app.state.mail.send(email, "account", text + "\nContact Zoqari if this was unexpected.")
    except Exception as exc:
        event("admin_account_mail_failed", error_type=type(exc).__name__)
        raise HTTPException(
            503, "Account notification could not be submitted; no account changes were saved."
        ) from None


def owner_guard(user):
    if user.organization_id and user.role == "OWNER":
        raise HTTPException(409, "Transfer organization ownership to an active verified replacement first.")


def unlink_employee(db, user, actor):
    employee = db.scalar(select(Employee).where(Employee.linked_user_id == user.id))
    if employee:
        db.add(
            EmployeeHierarchyChange(
                employee_id=employee.id, kind="user_link", previous_user_id=user.id, user_id=None, actor_id=actor.id
            )
        )
        employee.linked_user_id = None
        employee.revision += 1


def detail(db, user, settings):
    employee = (
        db.scalar(
            select(Employee).where(Employee.linked_user_id == user.id, Employee.organization_id == user.organization_id)
        )
        if user.organization_id
        else None
    )
    manager = db.get(Employee, employee.manager_id) if employee and employee.manager_id else None
    effective = bool(user.active and user.email_verified and operational_access(user.organization, settings))
    activity = db.scalars(
        select(PlatformEvent)
        .where(
            or_(
                PlatformEvent.details["user_id"].as_string() == user.id,
                PlatformEvent.details["old_owner_id"].as_string() == user.id,
                PlatformEvent.details["new_owner_id"].as_string() == user.id,
            )
        )
        .order_by(PlatformEvent.created_at.desc(), PlatformEvent.id)
        .limit(20)
    ).all()
    return {
        **user_view(user),
        "active": user.active,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "revision": user.admin_revision,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "deactivated_at": user.deactivated_at,
        "last_session_at": user.last_session_at,
        "operational_access": effective,
        "permissions": sorted(PERMISSIONS.get(user.role, set())) if effective and user.organization_id else [],
        "employee": {
            "id": employee.id,
            "name": employee.name,
            "revision": employee.revision,
            "manager_id": employee.manager_id,
            "manager_name": manager.name if manager else None,
        }
        if employee
        else None,
        "events": events(db, user_id=user.id),
        "last_login_at": user.last_login_at,
        "activity": [
            {
                "id": v.id,
                "action": v.action,
                "actor_id": v.actor_id,
                "created_at": v.created_at,
                "reason": v.reason,
                "details": v.details,
            }
            for v in activity
        ],
    }


@router.get("/users/{user_id}")
def user_detail(user_id: str, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    user = target(db, user_id)
    result = detail(db, user, request.app.state.settings)
    audit(db, actor, "user.view", user.organization_id, details={"user_id": user.id})
    db.commit()
    return result


@router.post("/users", status_code=201, dependencies=[Depends(limit)])
def create_user(body: Create, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(409, "An account already uses that email")
    user = User(
        email=body.email,
        name=(body.first_name + " " + body.last_name).strip(),
        first_name=body.first_name,
        last_name=body.last_name,
        role="EMPLOYEE",
        email_verified=False,
        password_hash=hasher.hash(secrets.token_urlsafe(48)),
    )
    db.add(user)
    try:
        db.flush()
        issue_code(db, user, request, preserve_challenge=True)
        send_token(db, user, "reset", request)
        audit(db, actor, "user.created", reason=body.reason, details={"user_id": user.id})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account already uses that email") from None
    return detail(db, user, request.app.state.settings)


@router.put("/users/{user_id}/profile")
def profile(user_id: str, body: Profile, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    user = locked_target(db, user_id, body)
    old_name = user.name
    user.first_name, user.last_name = body.first_name, body.last_name
    user.name = (body.first_name + " " + body.last_name).strip()
    record(db, actor, user, "user.profile_changed", body.reason, {"old_name": old_name, "new_name": user.name})
    db.commit()
    return detail(db, user, request.app.state.settings)


@router.put("/users/{user_id}/email", dependencies=[Depends(limit)])
def email(user_id: str, body: ChangeEmail, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    user = locked_target(db, user_id, body)
    owner_guard(user)
    if user.platform_authority and user.platform_authority.active:
        raise HTTPException(409, "Platform administrator email changes require a separate trusted recovery procedure")
    if user.email == body.email:
        raise HTTPException(409, "The account already uses this email")
    if db.scalar(select(User.id).where(User.email == body.email, User.id != user.id)):
        raise HTTPException(409, "An account already uses that email")
    old = user.email
    invalidate(db, user, invitations=True)
    db.execute(
        update(Invitation)
        .where(Invitation.email.in_([old, body.email]), Invitation.status == "pending")
        .values(status="revoked")
    )
    user.email, user.email_verified = body.email, False
    try:
        db.flush()
        notify(
            request,
            old,
            "An administrator requested a change to your Signal sign-in email. Existing sessions are revoked when the change is saved.",
        )
        issue_code(db, user, request, preserve_challenge=True)
        record(db, actor, user, "user.email_changed", body.reason, {"old_email": old, "new_email": user.email})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account already uses that email") from None
    return detail(db, user, request.app.state.settings)


@router.post("/users/{user_id}/status", dependencies=[Depends(limit)])
@router.put("/users/{user_id}/status", dependencies=[Depends(limit)])
def status(user_id: str, body: AccountStatus, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    user = locked_target(db, user_id, body)
    if not body.active:
        if not (user.organization and user.organization.suspended):
            owner_guard(user)
        if user.id == actor.id or (user.platform_authority and user.platform_authority.active):
            raise HTTPException(
                409, "Revoke platform authority through the trusted operator workflow before deactivation"
            )
    user.active = body.active
    user.deactivated_at = None if body.active else time.time()
    invalidate(db, user, invitations=True)
    notify(
        request,
        user.email,
        "Your Signal account has been "
        + ("reactivated." if body.active else "deactivated. Historical records are retained."),
    )
    account_event(
        db, "account_activated" if body.active else "account_deactivated", user=user, actor=actor, reason=body.reason
    )
    record(db, actor, user, "user.reactivated" if body.active else "user.deactivated", body.reason)
    db.commit()
    return detail(db, user, request.app.state.settings)


@router.put("/users/{user_id}/membership", dependencies=[Depends(limit)])
def membership(user_id: str, body: Membership, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    user = locked_target(db, user_id, body, body.organization_id)
    owner_guard(user)
    if body.organization_id and (not user.active or not user.email_verified):
        raise HTTPException(409, "Activate and verify the account before assigning membership")
    previous_org, previous_role = user.organization_id, user.role
    if previous_org != body.organization_id:
        unlink_employee(db, user, actor)
    user.organization_id, user.role = body.organization_id, body.role if body.organization_id else "EMPLOYEE"
    invalidate(db, user, invitations=True)
    notify(
        request,
        user.email,
        "Your Signal organization membership or customer role has changed. Sign in again to review your access.",
    )
    record(
        db,
        actor,
        user,
        "user.organization_changed" if previous_org != body.organization_id else "user.role_changed",
        body.reason,
        {
            "old_organization_id": previous_org,
            "new_organization_id": body.organization_id,
            "old_role": previous_role,
            "new_role": user.role,
        },
    )
    db.commit()
    db.expire(user, ["organization"])
    return detail(db, user, request.app.state.settings)


@router.post("/users/{user_id}/password-reset", dependencies=[Depends(limit)])
def password_reset(user_id: str, body: Mutation, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    user = locked_target(db, user_id, body)
    if not user.active:
        raise HTTPException(409, "Reactivate the account before requesting a password reset")
    try:
        send_token(db, user, "reset", request)
    except HTTPException as exc:
        db.rollback()
        account_event(db, "password_reset_request_failed", user=user, actor=actor, reason=body.reason)
        db.commit()
        raise exc
    account_event(db, "password_reset_requested_by_admin", user=user, actor=actor, reason=body.reason)
    record(db, actor, user, "user.password_reset_initiated", body.reason)
    db.commit()
    return {"message": "Password reset submitted through the configured mail provider. Delivery is not guaranteed."}


@router.post("/users/{user_id}/verification", dependencies=[Depends(limit)])
def verification(user_id: str, body: Mutation, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    user = locked_target(db, user_id, body)
    if not user.active or user.email_verified:
        raise HTTPException(409, "Verification requires an active, unverified account")
    try:
        issue_code(db, user, request, preserve_challenge=True)
    except HTTPException as exc:
        db.rollback()
        account_event(db, "verification_request_failed", user=user, actor=actor, reason=body.reason)
        db.commit()
        raise exc
    account_event(db, "verification_requested_by_admin", user=user, actor=actor, reason=body.reason)
    record(db, actor, user, "user.verification_requested", body.reason)
    db.commit()
    return {"message": "Verification submitted through the configured mail provider. Delivery is not guaranteed."}


@router.put("/users/{user_id}/employee-link")
def employee_link(
    user_id: str, body: EmployeeLink, request: Request, actor=Depends(platform_admin), db=Depends(get_db)
):
    user = locked_target(db, user_id, body)
    if not user.organization_id:
        raise HTTPException(409, "Assign organization membership before linking a tracked employee")
    chosen = (
        db.scalar(
            select(Employee).where(Employee.id == body.employee_id, Employee.organization_id == user.organization_id)
        )
        if body.employee_id
        else None
    )
    if body.employee_id and chosen is None:
        raise HTTPException(404, "Employee not found in this organization")
    if chosen and (
        not chosen.active or not user.active or (chosen.linked_user_id and chosen.linked_user_id != user.id)
    ):
        raise HTTPException(409, "Select an active unlinked employee and an active account")
    unlink_employee(db, user, actor)
    if chosen:
        chosen.linked_user_id = user.id
        chosen.revision += 1
        db.add(
            EmployeeHierarchyChange(
                employee_id=chosen.id, kind="user_link", previous_user_id=None, user_id=user.id, actor_id=actor.id
            )
        )
    record(db, actor, user, "user.employee_link_changed", body.reason, {"employee_id": body.employee_id})
    db.commit()
    return detail(db, user, request.app.state.settings)


@router.put("/users/{user_id}/manager")
def manager(user_id: str, body: Manager, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    user = locked_target(db, user_id, body)
    employee = (
        db.scalar(
            select(Employee).where(Employee.linked_user_id == user.id, Employee.organization_id == user.organization_id)
        )
        if user.organization_id
        else None
    )
    if not employee:
        raise HTTPException(409, "Link the account to a tracked employee first")
    if employee.revision != body.employee_revision:
        raise HTTPException(409, "Employee changed. Reload the account")
    old = employee.manager_id
    set_manager(db, employee, body.manager_id, actor)
    employee.revision += 1
    record(
        db,
        actor,
        user,
        "user.manager_changed",
        body.reason,
        {"employee_id": employee.id, "old_manager_id": old, "new_manager_id": body.manager_id},
    )
    db.commit()
    return detail(db, user, request.app.state.settings)


@router.put("/organizations/{organization_id}/owner", dependencies=[Depends(limit)])
def transfer_owner(
    organization_id: str, body: OwnerTransfer, request: Request, actor=Depends(platform_admin), db=Depends(get_db)
):
    organization(db, organization_id, lock=True)
    owners = db.scalars(select(User).where(User.organization_id == organization_id, User.role == "OWNER")).all()
    if len(owners) != 1 or owners[0].id != body.current_owner_id or body.current_owner_id == body.new_owner_id:
        raise HTTPException(409, "Current Owner changed or is ambiguous. Refresh and select a different replacement")
    for uid in sorted([body.current_owner_id, body.new_owner_id]):
        db.execute(update(User).where(User.id == uid).values(active=User.active))
    old, new = target(db, body.current_owner_id), target(db, body.new_owner_id)
    db.refresh(old)
    db.refresh(new)
    if new.organization_id != organization_id or not new.active or not new.email_verified:
        raise HTTPException(409, "Replacement must be an active verified member of this organization")
    old.role, new.role = "ADMIN", "OWNER"
    invalidate(db, old, invitations=True)
    invalidate(db, new, invitations=True)
    notify(
        request,
        old.email,
        "Your Signal organization ownership was transferred to another member. Your account remains an Admin.",
    )
    notify(
        request,
        new.email,
        "You are now the Owner of your Signal organization. Sign in again to review access and billing.",
    )
    for user in (old, new):
        user.admin_revision += 1
        user.updated_at = time.time()
    audit(db, actor, "owner.changed", organization_id, body.reason, {"old_owner_id": old.id, "new_owner_id": new.id})
    db.commit()
    return {
        "message": "Ownership transferred. Both members must sign in again.",
        "old_owner_id": old.id,
        "new_owner_id": new.id,
    }
