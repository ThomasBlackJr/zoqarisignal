"""Explicit platform metadata/control boundary. No tenant impersonation, passwords or codes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, field_validator
from sqlalchemy import delete, func, or_, select, update
from .auth import current_user, get_db, user_view
from .account_routes import limit, send_token
from .models import AccountEvent, EntitlementEvent, Organization, PlatformAdministrator, Role, Session, User
from .schemas import StrictModel
from .services.account_audit import account_event
from .services.entitlements import operational_access
from .services.pilot import change_pilot
from .services.verification import issue_code

router = APIRouter(prefix="/platform", tags=["platform"])


def platform_admin(user=Depends(current_user), db=Depends(get_db)):
    authority = db.get(PlatformAdministrator, user.id)
    if not user.email_verified or not authority or not authority.active:
        raise HTTPException(403, "Platform administrator access required")
    return user


class Reason(StrictModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A reason is required")
        return value.strip()


class Active(Reason):
    active: bool = Field(strict=True)


class BetaReason(StrictModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def optional_note(cls, value):
        return value.strip() or None if value is not None else None


class Pilot(BetaReason):
    expires_at: float | None = Field(default=None, allow_inf_nan=False)


class Suspension(Reason):
    suspended: bool = Field(strict=True)


def owned_user(db, user_id, lock=False):
    if lock:
        db.execute(update(User).where(User.id == user_id).values(active=User.active))
    user = db.get(User, user_id, populate_existing=True)
    if user is None:
        raise HTTPException(404, "Account not found")
    return user


def organization(db, organization_id):
    value = db.get(Organization, organization_id)
    if value is None:
        raise HTTPException(404, "Organization not found")
    return value


def user_detail(user):
    return {
        **user_view(user),
        "active": user.active,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


def organization_detail(db, value, settings):
    owners = db.scalars(select(User).where(User.organization_id == value.id, User.role == Role.OWNER)).all()
    return {
        "id": value.id,
        "name": value.name,
        "created_at": value.created_at,
        "suspended": value.suspended,
        "member_count": db.scalar(select(func.count()).select_from(User).where(User.organization_id == value.id)),
        "owners": [{"name": o.name, "email": o.email, "active": o.active} for o in owners],
        "operational_access": operational_access(value, settings),
        "signal_access": ("BETA" if value.entitlement_source == "pilot" else "ACTIVE")
        if operational_access(value, settings)
        else "NO ACCESS",
        "beta_access": value.entitlement_source == "pilot" and operational_access(value, settings),
        "pilot_approved": value.entitlement_source == "pilot" and value.subscription_status == "active",
        "pilot_expires_at": value.entitlement_expires_at if value.entitlement_source == "pilot" else None,
        "source": value.entitlement_source,
    }


def events(db, *, user_id=None, organization_id=None):
    query = select(AccountEvent)
    if user_id:
        query = query.where(AccountEvent.user_id == user_id)
    if organization_id:
        query = query.where(AccountEvent.organization_id == organization_id)
    rows = db.scalars(query.order_by(AccountEvent.created_at.desc(), AccountEvent.id.desc()).limit(50)).all()
    return [
        {
            "action": e.action,
            "created_at": e.created_at,
            "reason": e.reason,
            "actor": db.get(User, e.actor_id).name if e.actor_id and db.get(User, e.actor_id) else "Account request",
        }
        for e in rows
    ]


@router.get("/session")
def session(actor=Depends(platform_admin)):
    return user_detail(actor)


@router.get("/users")
def users(
    q: str = Query("", max_length=120), offset: int = Query(0, ge=0), actor=Depends(platform_admin), db=Depends(get_db)
):
    query = select(User).where(
        or_(User.email.icontains(q.strip(), autoescape=True), User.name.icontains(q.strip(), autoescape=True))
    )
    return {
        "total": db.scalar(select(func.count()).select_from(query.subquery())),
        "items": [user_detail(u) for u in db.scalars(query.order_by(User.email).offset(offset).limit(25))],
    }


@router.get("/users/{user_id}")
def user(user_id: str, actor=Depends(platform_admin), db=Depends(get_db)):
    return {**user_detail(owned_user(db, user_id)), "events": events(db, user_id=user_id)}


@router.post("/users/{user_id}/status")
def status(user_id: str, body: Active, actor=Depends(platform_admin), db=Depends(get_db)):
    target = owned_user(db, user_id, lock=True)
    authority = db.get(PlatformAdministrator, target.id)
    if authority and authority.active:
        raise HTTPException(409, "Platform operator accounts require trusted server management")
    if not body.active and target.role == Role.OWNER and target.organization_id:
        db.execute(update(Organization).where(Organization.id == target.organization_id).values(id=Organization.id))
        org = db.get(Organization, target.organization_id, populate_existing=True)
        others = db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.organization_id == org.id,
                User.id != target.id,
                User.role == Role.OWNER,
                User.active.is_(True),
                User.email_verified.is_(True),
            )
        )
        if not org.suspended and not others:
            raise HTTPException(409, "Suspend the organization before disabling its only active Owner")
    target.active = body.active
    db.execute(delete(Session).where(Session.user_id == target.id))
    account_event(
        db, "account_activated" if body.active else "account_deactivated", user=target, actor=actor, reason=body.reason
    )
    db.commit()
    return user_detail(target)


@router.post("/users/{user_id}/verification", dependencies=[Depends(limit)])
def verification(user_id: str, body: Reason, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    target = owned_user(db, user_id)
    if target.email_verified or not target.active:
        raise HTTPException(409, "Verification requires an active unverified account")
    try:
        issue_code(db, target, request, preserve_challenge=True)
    except HTTPException as exc:
        db.rollback()
        account_event(db, "verification_request_failed", user=target, actor=actor, reason=body.reason)
        db.commit()
        raise exc
    account_event(db, "verification_requested_by_admin", user=target, actor=actor, reason=body.reason)
    db.commit()
    return {"message": "Verification email submitted. No code or credentials are displayed here."}


@router.post("/users/{user_id}/password-reset", dependencies=[Depends(limit)])
def password_reset(user_id: str, body: Reason, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    target = owned_user(db, user_id)
    if not target.active:
        raise HTTPException(409, "Activate the account before requesting recovery")
    try:
        send_token(db, target, "reset", request)
    except HTTPException as exc:
        db.rollback()
        account_event(db, "password_reset_request_failed", user=target, actor=actor, reason=body.reason)
        db.commit()
        raise exc
    account_event(db, "password_reset_requested_by_admin", user=target, actor=actor, reason=body.reason)
    db.commit()
    return {"message": "Password reset email submitted. The user chooses the new password."}


@router.get("/organizations")
def organizations(
    request: Request,
    q: str = Query("", max_length=120),
    offset: int = Query(0, ge=0),
    actor=Depends(platform_admin),
    db=Depends(get_db),
):
    query = select(Organization).where(Organization.name.icontains(q.strip(), autoescape=True))
    return {
        "total": db.scalar(select(func.count()).select_from(query.subquery())),
        "items": [
            organization_detail(db, o, request.app.state.settings)
            for o in db.scalars(query.order_by(Organization.name, Organization.id).offset(offset).limit(25))
        ],
    }


@router.get("/organizations/{organization_id}")
def org(organization_id: str, request: Request, actor=Depends(platform_admin), db=Depends(get_db)):
    value = organization(db, organization_id)
    history = db.scalars(
        select(EntitlementEvent)
        .where(EntitlementEvent.organization_id == organization_id)
        .order_by(EntitlementEvent.created_at.desc())
        .limit(50)
    ).all()
    return {
        **organization_detail(db, value, request.app.state.settings),
        "users": [
            user_detail(u)
            for u in db.scalars(select(User).where(User.organization_id == value.id).order_by(User.email).limit(100))
        ],
        "events": events(db, organization_id=value.id),
        "pilot_history": [
            {
                "action": e.action,
                "created_at": e.created_at,
                "expires_at": e.expires_at,
                "reason": e.reason,
                "actor": db.get(User, e.actor_id).name,
            }
            for e in history
        ],
    }


def pilot_change(db, organization_id, actor, body, revoke):
    value = organization(db, organization_id)
    try:
        change_pilot(
            db,
            value.id,
            value.name,
            actor.email,
            body.reason or ("Beta access revoked" if revoke else "Beta access granted or renewed"),
            revoke=revoke,
            expires_at=None if revoke else body.expires_at,
            platform_actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"message": "Beta access revoked" if revoke else "Beta access granted"}


@router.post("/organizations/{organization_id}/pilot")
def grant(organization_id: str, body: Pilot, actor=Depends(platform_admin), db=Depends(get_db)):
    return pilot_change(db, organization_id, actor, body, False)


@router.post("/organizations/{organization_id}/pilot/revoke")
def revoke(organization_id: str, body: BetaReason, actor=Depends(platform_admin), db=Depends(get_db)):
    return pilot_change(db, organization_id, actor, body, True)


@router.post("/organizations/{organization_id}/suspension")
def suspend(organization_id: str, body: Suspension, actor=Depends(platform_admin), db=Depends(get_db)):
    db.execute(update(Organization).where(Organization.id == organization_id).values(id=Organization.id))
    value = organization(db, organization_id)
    value.suspended = body.suspended
    account_event(
        db,
        "organization_suspended" if body.suspended else "organization_resumed",
        organization_id=value.id,
        actor=actor,
        reason=body.reason,
    )
    db.commit()
    return {"message": "Organization paused" if body.suspended else "Organization resumed"}
