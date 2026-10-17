"""Separate platform authority. No customer-role elevation or impersonation."""

import time
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, select, update

from .auth import current_user, get_db, user_view, token_hash, find_user
from .account_schemas import OrganizationCreate, Email
from .logging import event
from .models import (
    BetaAccess,
    Call,
    Evaluation,
    Invitation,
    Organization,
    PlatformAdministrator,
    PlatformEvent,
    User,
    Employee,
)
from .schemas import StrictModel
from .services.entitlements import operational_access
from .services.hierarchy import lock_organization
from .services.rubric import create_starter_rubric
from .team_routes import invite_view

router = APIRouter(prefix="/platform", tags=["platform"])


def platform_admin(user=Depends(current_user), db=Depends(get_db)):
    authority = db.get(PlatformAdministrator, user.id)
    if not user.email_verified or not authority or not authority.active:
        raise HTTPException(403, "Platform administrator access required")
    return user


def audit(db, actor, action, organization_id=None, reason="Platform inspection", details=None):
    db.add(
        PlatformEvent(actor_id=actor.id, action=action, organization_id=organization_id, reason=reason, details=details)
    )


@router.get("/session")
def session(actor=Depends(platform_admin), db=Depends(get_db)):
    result = user_view(actor)
    audit(db, actor, "platform.session")
    db.commit()
    return result


@router.get("/summary")
def summary(actor=Depends(platform_admin), db=Depends(get_db)):
    result = {
        "organizations": db.scalar(select(func.count()).select_from(Organization)),
        "users": db.scalar(select(func.count()).select_from(User)),
        "suspended": db.scalar(select(func.count()).select_from(Organization).where(Organization.suspended.is_(True))),
        "calls": db.scalar(select(func.count()).select_from(Call)),
    }
    audit(db, actor, "platform.summary")
    db.commit()
    return result


@router.get("/users")
def users(
    q: str = Query("", max_length=120),
    organization_id: str | None = None,
    role: Literal["OWNER", "ADMIN", "MANAGER", "REVIEWER", "EMPLOYEE", "SUPERVISOR"] | None = None,
    status: Literal["active", "disabled", "unverified"] | None = None,
    offset: int = Query(0, ge=0),
    actor=Depends(platform_admin),
    db=Depends(get_db),
):
    query = select(User).where(
        User.name.icontains(q.strip(), autoescape=True) | User.email.icontains(q.strip(), autoescape=True)
    )
    if organization_id:
        organization(db, organization_id)
        query = query.where(User.organization_id == organization_id)
    if role:
        query = query.where(User.role == role)
    if status == "active":
        query = query.where(User.active.is_(True))
    elif status == "disabled":
        query = query.where(User.active.is_(False))
    elif status == "unverified":
        query = query.where(User.email_verified.is_(False))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(User.name, User.id).offset(offset).limit(50)).all()
    result = {"total": total, "items": [{**user_view(u), "active": u.active} for u in rows]}
    audit(db, actor, "users.view", organization_id)
    db.commit()
    return result


@router.get("/organizations/{organization_id}/employees")
def employees(
    organization_id: str,
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=120),
    actor=Depends(platform_admin),
    db=Depends(get_db),
):
    from .employee_routes import employee_view

    organization(db, organization_id)
    query = select(Employee).where(
        Employee.organization_id == organization_id, Employee.name.icontains(q.strip(), autoescape=True)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Employee.name, Employee.id).offset(offset).limit(50)).all()
    result = {"total": total, "items": [employee_view(e) for e in rows]}
    audit(db, actor, "employees.view", organization_id)
    db.commit()
    return result


def organization(db, organization_id, lock=False):
    if lock:
        lock_organization(db, organization_id)
    value = db.get(Organization, organization_id, populate_existing=True)
    if value is None:
        raise HTTPException(404, "Organization not found")
    return value


def view(value, settings):
    beta = value.beta_access
    return {
        "id": value.id,
        "name": value.name,
        "created_at": value.created_at,
        "suspended": value.suspended,
        "operational_access": operational_access(value, settings),
        "subscription_status": value.subscription_status,
        "beta_access": {"active": beta.active, "expires_at": beta.expires_at} if beta else None,
    }


class Reason(StrictModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A reason is required")
        return value.strip()


class Suspension(Reason):
    suspended: bool = Field(strict=True)


class Grant(Reason):
    expires_at: float | None = Field(default=None, allow_inf_nan=False)

    @field_validator("expires_at")
    @classmethod
    def future(cls, value):
        if value is not None and value <= time.time():
            raise ValueError("Expiration must be in the future")
        return value


class CreateOrganization(OrganizationCreate, Reason):
    pass


class PlatformInvite(Email, Reason):
    role: Literal["OWNER", "ADMIN", "MANAGER", "REVIEWER", "EMPLOYEE"]
    purpose: Literal["team", "owner_replacement"] = "team"
    confirmed: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def replacement_confirmation(self):
        if self.purpose == "owner_replacement" and not self.confirmed:
            raise ValueError("Explicit confirmation is required for a replacement Owner invitation")
        return self


@router.get("/organizations")
def organizations(
    request: Request,
    q: str = Query("", max_length=120),
    offset: int = Query(0, ge=0),
    actor=Depends(platform_admin),
    db=Depends(get_db),
):
    query = select(Organization).where(Organization.name.icontains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    values = db.scalars(query.order_by(Organization.name, Organization.id).offset(offset).limit(50)).all()
    result = {"total": total, "items": [view(v, request.app.state.settings) for v in values]}
    audit(db, actor, "organizations.view")
    db.commit()
    return result


@router.post("/organizations", status_code=201)
def create(body: CreateOrganization, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    value = Organization(name=body.name)
    db.add(value)
    db.flush()
    create_starter_rubric(db, value.id, actor.id)
    audit(db, actor, "organization.create", value.id, body.reason)
    db.commit()
    return view(value, request.app.state.settings)


@router.get("/organizations/{organization_id}")
def details(organization_id: str, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    value = organization(db, organization_id)
    result = view(value, request.app.state.settings)
    result["usage"] = {
        "calls_uploaded": db.scalar(select(func.count()).select_from(Call).where(Call.organization_id == value.id)),
        "calls_processed": db.scalar(
            select(func.count()).select_from(Call).where(Call.organization_id == value.id, Call.status == "completed")
        ),
        "qa_evaluations": db.scalar(
            select(func.count()).select_from(Evaluation).join(Call).where(Call.organization_id == value.id)
        ),
        "reviews_completed": db.scalar(
            select(func.count())
            .select_from(Evaluation)
            .join(Call)
            .where(Call.organization_id == value.id, Evaluation.reviewed_at.is_not(None))
        ),
    }
    audit(db, actor, "organization.view", value.id)
    db.commit()
    return result


@router.get("/organizations/{organization_id}/members")
def members(organization_id: str, offset: int = Query(0, ge=0), actor=Depends(platform_admin), db=Depends(get_db)):
    organization(db, organization_id)
    users = db.scalars(
        select(User).where(User.organization_id == organization_id).order_by(User.id).offset(offset).limit(50)
    ).all()
    result = {"items": [{**user_view(u), "active": u.active} for u in users]}
    audit(db, actor, "members.view", organization_id)
    db.commit()
    return result


@router.get("/organizations/{organization_id}/invitations")
def invitations(organization_id: str, offset: int = Query(0, ge=0), actor=Depends(platform_admin), db=Depends(get_db)):
    organization(db, organization_id)
    result = {
        "items": [
            invite_view(i)
            for i in db.scalars(
                select(Invitation)
                .where(Invitation.organization_id == organization_id)
                .order_by(Invitation.created_at.desc(), Invitation.id)
                .offset(offset)
                .limit(50)
            )
        ]
    }
    audit(db, actor, "invitations.view", organization_id)
    db.commit()
    return result


@router.post("/organizations/{organization_id}/invitations/{invitation_id}/revoke")
def revoke_invitation(
    organization_id: str, invitation_id: str, body: Reason, actor=Depends(platform_admin), db=Depends(get_db)
):
    organization(db, organization_id, lock=True)
    invitation = db.scalar(
        select(Invitation).where(Invitation.id == invitation_id, Invitation.organization_id == organization_id)
    )
    if invitation is None:
        raise HTTPException(404, "Invitation not found")
    if invitation.status == "pending":
        invitation.status = "revoked"
    audit(db, actor, "invitation.revoke", organization_id, body.reason, {"invitation_id": invitation_id})
    db.commit()
    return {"message": "Pending invitation revoked"}


@router.post("/organizations/{organization_id}/invitations", status_code=201)
def invite(
    organization_id: str, body: PlatformInvite, request: Request, actor=Depends(platform_admin), db=Depends(get_db)
):
    organization(db, organization_id, lock=True)
    if body.purpose == "owner_replacement" and body.role != "ADMIN":
        raise HTTPException(422, "A replacement candidate joins as Admin; ownership requires separate confirmation")
    existing = find_user(db, body.email)
    if existing and existing.organization_id:
        raise HTTPException(409, "This account already belongs to an organization")
    if body.role == "OWNER" and db.scalar(
        select(User.id).where(User.organization_id == organization_id, User.role == "OWNER")
    ):
        raise HTTPException(409, "Organization already has an Owner; use the separately confirmed ownership transfer")
    if body.role == "OWNER" and db.scalar(
        select(Invitation.id).where(
            Invitation.organization_id == organization_id,
            Invitation.role == "OWNER",
            Invitation.status == "pending",
            Invitation.expires_at > time.time(),
        )
    ):
        raise HTTPException(409, "Revoke the pending Owner invitation before issuing another")
    db.execute(
        update(Invitation)
        .where(
            Invitation.organization_id == organization_id,
            Invitation.email == body.email,
            Invitation.status == "pending",
        )
        .values(status="revoked")
    )
    token = secrets.token_urlsafe(32)
    value = Invitation(
        organization_id=organization_id,
        invited_by=actor.id,
        email=body.email,
        role=body.role,
        platform_issued=True,
        token_hash=token_hash(token),
        expires_at=time.time() + 48 * 3600,
    )
    db.add(value)
    db.flush()
    try:
        request.app.state.mail.send(
            body.email,
            "invite",
            (
                "You are invited as a replacement Owner candidate. Accepting joins the organization as Admin. Ownership requires a separate confirmed platform transfer.\n\n"
                if body.purpose == "owner_replacement"
                else ""
            )
            + request.app.state.settings.frontend_origin
            + "/accept-invitation#token="
            + token,
        )
    except Exception as exc:
        event("platform_invitation_mail_failed", error_type=type(exc).__name__)
        raise HTTPException(503, "Invitation delivery is unavailable") from None
    audit(
        db,
        actor,
        "invitation.create",
        organization_id,
        body.reason,
        {"invitation_id": value.id, "role": body.role, "purpose": body.purpose},
    )
    db.commit()
    return invite_view(value)


@router.put("/organizations/{organization_id}/suspension")
def suspend(
    organization_id: str, body: Suspension, request: Request, actor=Depends(platform_admin), db=Depends(get_db)
):
    value = organization(db, organization_id, lock=True)
    value.suspended = body.suspended
    audit(db, actor, "organization.suspend" if body.suspended else "organization.reactivate", value.id, body.reason)
    db.commit()
    return view(value, request.app.state.settings)


@router.put("/organizations/{organization_id}/beta-access")
def grant(organization_id: str, body: Grant, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    value = organization(db, organization_id, lock=True)
    beta = value.beta_access
    if beta is None:
        beta = BetaAccess(organization_id=value.id)
        value.beta_access = beta
    beta.active, beta.expires_at = True, body.expires_at
    # Include the actual expiration in the immutable audit, not only the mutable grant.
    audit(db, actor, "beta.grant", value.id, body.reason, {"expires_at": body.expires_at})
    db.commit()
    return view(value, request.app.state.settings)


@router.delete("/organizations/{organization_id}/beta-access")
def revoke_beta(
    organization_id: str, body: Reason, request: Request, actor=Depends(platform_admin), db=Depends(get_db)
):
    value = organization(db, organization_id, lock=True)
    if value.beta_access:
        value.beta_access.active = False
    audit(db, actor, "beta.revoke", value.id, body.reason)
    db.commit()
    return view(value, request.app.state.settings)


@router.get("/activity")
def activity(offset: int = Query(0, ge=0), actor=Depends(platform_admin), db=Depends(get_db)):
    rows = db.scalars(
        select(PlatformEvent).order_by(PlatformEvent.created_at.desc(), PlatformEvent.id).offset(offset).limit(50)
    ).all()
    result = {
        "items": [
            {
                "id": v.id,
                "actor_id": v.actor_id,
                "actor_name": db.get(User, v.actor_id).name,
                "organization_id": v.organization_id,
                "organization_name": db.get(Organization, v.organization_id).name if v.organization_id else None,
                "action": v.action,
                "reason": v.reason,
                "details": v.details,
                "created_at": v.created_at,
            }
            for v in rows
        ]
    }
    audit(db, actor, "activity.view")
    db.commit()
    return result
