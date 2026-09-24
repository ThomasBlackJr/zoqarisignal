"""Organization-scoped invitations; possession never replaces existing account authentication."""

import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .account_routes import issue_session, limit
from .account_schemas import Email, Registration, Token
from .auth import current_user, find_user, get_db, hasher, require, token_hash, user_view
from .logging import event
from .models import Invitation, Organization, User

router = APIRouter()


class Invite(Email):
    role: Literal["ADMIN", "MANAGER", "REVIEWER", "EMPLOYEE"]


class Join(Token, Registration):
    pass


def invite_view(i):
    return {
        "id": i.id,
        "email": i.email,
        "role": i.role,
        "created_at": i.created_at,
        "expires_at": i.expires_at,
        "status": i.status if i.status != "pending" or i.expires_at > time.time() else "expired",
    }


@router.get("/team")
def team(user=Depends(require("manage_users")), db=Depends(get_db)):
    return {
        "users": [
            {**user_view(u), "active": u.active}
            for u in db.scalars(select(User).where(User.organization_id == user.organization_id).order_by(User.name))
        ],
        "invitations": [
            invite_view(i)
            for i in db.scalars(
                select(Invitation)
                .where(Invitation.organization_id == user.organization_id)
                .order_by(Invitation.created_at.desc())
                .limit(100)
            )
        ],
    }


@router.post("/invitations", status_code=201, dependencies=[Depends(limit)])
def invite(body: Invite, request: Request, user=Depends(require("manage_users")), db=Depends(get_db)):
    # Serialize replacement. Only the latest pending invitation for this email is valid.
    db.execute(update(Organization).where(Organization.id == user.organization_id).values(name=Organization.name))
    existing = find_user(db, body.email)
    if existing and existing.organization_id:
        raise HTTPException(409, "This account already belongs to an organization.")
    db.execute(
        update(Invitation)
        .where(
            Invitation.organization_id == user.organization_id,
            Invitation.email == body.email,
            Invitation.status == "pending",
        )
        .values(status="revoked")
    )
    token = secrets.token_urlsafe(32)
    value = Invitation(
        organization_id=user.organization_id,
        invited_by=user.id,
        email=body.email,
        role=body.role,
        token_hash=token_hash(token),
        expires_at=time.time() + 48 * 3600,
    )
    db.add(value)
    db.flush()
    try:
        request.app.state.mail.send(
            body.email, "invite", request.app.state.settings.frontend_origin + "/accept-invitation#token=" + token
        )
    except Exception as exc:
        event("invitation_mail_failed", error_type=type(exc).__name__)
        raise HTTPException(503, "Invitation delivery is unavailable. Check account email configuration.") from None
    db.commit()
    return {**invite_view(value), "mail_delivery": request.app.state.settings.mail_delivery}


@router.post("/invitations/{invitation_id}/revoke")
def revoke(invitation_id: str, user=Depends(require("manage_users")), db=Depends(get_db)):
    value = db.scalar(
        select(Invitation).where(Invitation.id == invitation_id, Invitation.organization_id == user.organization_id)
    )
    if value is None:
        raise HTTPException(404, "Invitation not found")
    db.execute(
        update(Invitation).where(Invitation.id == value.id, Invitation.status == "pending").values(status="revoked")
    )
    db.commit()
    return {"message": "Pending invitation revoked"}


def resolve(db, token, consume=False):
    conditions = (
        Invitation.token_hash == token_hash(token),
        Invitation.status == "pending",
        Invitation.expires_at > time.time(),
    )
    if consume:
        invitation_id = db.execute(
            update(Invitation).where(*conditions).values(status="accepted").returning(Invitation.id)
        ).scalar_one_or_none()
        value = db.get(Invitation, invitation_id) if invitation_id else None
    else:
        value = db.scalar(select(Invitation).where(*conditions))
    inviter = db.get(User, value.invited_by) if value else None
    if (
        not value
        or not inviter
        or not inviter.active
        or inviter.organization_id != value.organization_id
        or inviter.role not in {"OWNER", "ADMIN"}
    ):
        raise HTTPException(400, "Invitation is invalid, expired, revoked, or already accepted.")
    return value


@router.post("/invitations/preview", dependencies=[Depends(limit)])
def preview(body: Token, db=Depends(get_db)):
    value = resolve(db, body.token)
    return {
        "organization_name": db.get(Organization, value.organization_id).name,
        "email": value.email,
        "role": value.role,
    }


@router.post("/invitations/accept", dependencies=[Depends(limit)])
def accept(body: Token, user=Depends(current_user), db=Depends(get_db)):
    value = resolve(db, body.token, consume=True)
    if user.email != value.email:
        raise HTTPException(403, "Sign in with the invited email address.")
    changed = db.execute(
        update(User)
        .where(User.id == user.id, User.organization_id.is_(None), User.active.is_(True))
        .values(organization_id=value.organization_id, role=value.role, email_verified=True)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Your account already belongs to an organization.")
    value.accepted_by = user.id
    value.accepted_at = time.time()
    db.commit()
    return {"message": "Joined the existing organization"}


@router.post("/invitations/register", status_code=201, dependencies=[Depends(limit)])
def register(body: Join, request: Request, response: Response, db=Depends(get_db)):
    value = resolve(db, body.token, consume=True)
    if body.email != value.email:
        raise HTTPException(403, "Use the invited email address.")
    if find_user(db, body.email):
        raise HTTPException(409, "An account exists. Choose Sign in to accept; its password will not be changed.")
    user = User(
        email=value.email,
        name=body.name,
        password_hash=hasher.hash(body.password),
        role=value.role,
        organization_id=value.organization_id,
        email_verified=True,
    )
    db.add(user)
    try:
        db.flush()
        value.accepted_by = user.id
        value.accepted_at = time.time()
        issue_session(db, user, request, response)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account exists. Sign in to accept.") from None
    return user_view(user)
