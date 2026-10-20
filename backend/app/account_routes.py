"""Customer account entry. Operational routes continue to use the existing provider abstraction."""

import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, update, and_, or_
from sqlalchemy.exc import IntegrityError

from .account_schemas import CompleteSetup, Email, OrganizationCreate, Registration, Reset
from .auth import COOKIE, current_user, find_user, get_db, hasher, require, token_hash, user_view, verify
from .logging import event
from .models import AccountToken, Call, EntitlementEvent, Invitation, Organization, Role, Session, User
from .services.account_audit import account_event
from .services.entitlements import operational_access, access_expiration, INACTIVE_ACCESS_MESSAGE
from .services.rubric import create_starter_rubric
from .services.verification import issue_code, redeem_code
from .models import VerificationCode
from .schemas import StrictModel
from pydantic import Field

router = APIRouter()


class AccountLimiter:
    """Bounded single-process abuse limiter; deploy an edge limiter before public launch."""

    def __init__(self):
        self.lock = threading.Lock()
        self.entries = defaultdict(deque)

    def check(self, key):
        now = time.time()
        with self.lock:
            for old in [k for k, v in self.entries.items() if not v or v[-1] < now - 3600]:
                del self.entries[old]
            if key not in self.entries and len(self.entries) >= 5000:
                raise HTTPException(429, "Account requests are busy. Try again later.")
            queue = self.entries[key]
            while queue and queue[0] < now - 3600:
                queue.popleft()
            if len(queue) >= 20:
                raise HTTPException(429, "Too many account requests. Try again in an hour.")
            queue.append(now)


def limit(request: Request):
    request.app.state.account_limiter.check(request.client.host if request.client else "unknown")


def issue_session(db, user, request, response):
    settings = request.app.state.settings
    now = time.time()
    user.last_session_at = now
    old = request.cookies.get(COOKIE)
    if old:
        db.execute(delete(Session).where(Session.token_hash == token_hash(old)))
    db.execute(delete(Session).where(Session.expires_at <= now))
    token = secrets.token_urlsafe(32)
    seconds = settings.session_hours * 3600
    db.add(Session(token_hash=token_hash(token), user_id=user.id, expires_at=now + seconds))
    user.last_session_at = now
    user.last_login_at = now
    account_event(db, "session_started", user=user, actor=user)
    db.commit()
    response.set_cookie(
        COOKIE, token, max_age=seconds, httponly=True, secure=settings.cookie_secure, samesite="strict", path="/"
    )


def send_token(db, user, purpose, request):
    if purpose != "reset":
        raise ValueError("Verification uses issue_code; this helper issues password-reset links only")
    # Serialize token replacement for this account, including concurrent resend requests.
    db.execute(update(User).where(User.id == user.id).values(active=User.active))
    db.execute(delete(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == purpose))
    token = secrets.token_urlsafe(32)
    lifetime = 1800
    db.add(
        AccountToken(token_hash=token_hash(token), user_id=user.id, purpose=purpose, expires_at=time.time() + lifetime)
    )
    path = "reset-password"
    # Fragment never reaches HTTP access logs or Referer headers.
    link = request.app.state.settings.frontend_origin + "/" + path + "#token=" + token
    try:
        request.app.state.mail.send(user.email, purpose, link)
    except Exception as exc:
        event("account_mail_failed", error_type=type(exc).__name__)
        raise HTTPException(
            503, "Account email delivery is unavailable. Contact the administrator or try again later."
        ) from None


def consume_token(db, token, purpose):
    # Atomic consumption: at most one concurrent request may redeem a token.
    user_id = db.execute(
        delete(AccountToken)
        .where(
            AccountToken.token_hash == token_hash(token),
            AccountToken.purpose == purpose,
            AccountToken.expires_at > time.time(),
        )
        .returning(AccountToken.user_id)
    ).scalar_one_or_none()
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.active:
        raise HTTPException(400, "This link is invalid, expired, or already used. Request a new link.")
    return user


@router.get("/auth/options")
def options(request: Request):
    mode = request.app.state.settings.mail_delivery
    return {"registration_available": mode != "disabled", "mail_delivery": mode}


@router.post("/auth/register", status_code=201, dependencies=[Depends(limit)])
def register(body: Registration, request: Request, response: Response, db=Depends(get_db)):
    if request.app.state.settings.mail_delivery == "disabled":
        raise HTTPException(503, "Registration requires configured account email delivery.")
    # Public responses conceal address state; proven existing credentials may sign in.
    password_hash = hasher.hash(body.password)
    existing = find_user(db, body.email)
    if existing:
        # Correct existing credentials are authentication, not public account disclosure.
        # Continue as sign-in instead of pretending a verified account needs a new code.
        if verify(body.password, existing.password_hash):
            if not existing.active:
                raise HTTPException(403, "Your account is inactive. Contact Zoqari or your organization Owner.")
            issue_session(db, existing, request, response)
            return {**registration_view(secrets.token_urlsafe(32), request), "signed_in": True}
        # A repeat signup must never replace credentials or reveal account status.
        # Unverified recipients may request another code after the same persisted cooldown.
        if existing.active and not existing.email_verified:
            try:
                challenge = issue_code(db, existing, request)
                account_event(db, "verification_requested", user=existing)
                db.commit()
                return registration_view(challenge, request)
            except HTTPException:
                db.rollback()
        return registration_view(secrets.token_urlsafe(32), request)
    user = User(
        email=body.email,
        name=body.name,
        password_hash=password_hash,
        role=Role.EMPLOYEE,
        email_verified=False,
    )
    db.add(user)
    try:
        db.flush()
        challenge = issue_code(db, user, request)
        account_event(db, "account_registered", user=user)
        db.commit()
    except IntegrityError:
        db.rollback()
        return registration_view(secrets.token_urlsafe(32), request)
    except HTTPException as exc:
        db.rollback()
        if exc.status_code != 503:
            raise
        # Delivery errors must not distinguish a new address from an existing
        # one. The sanitized operator event remains available for diagnosis.
        return registration_view(secrets.token_urlsafe(32), request)
    return registration_view(challenge, request)


def registration_view(challenge, request):
    return {
        "message": "If this address can register, a verification code has been requested. Existing customers can sign in or reset their password.",
        "challenge": challenge,
        "mail_delivery": request.app.state.settings.mail_delivery,
        "resend_after": 60,
    }


class CodeBody(StrictModel):
    code: str = Field(pattern=r"^[0-9]{6}$")
    challenge: str | None = Field(default=None, min_length=40, max_length=100)


class ResendCode(StrictModel):
    challenge: str = Field(min_length=40, max_length=100)


@router.post("/auth/verification", dependencies=[Depends(limit)])
def resend(request: Request, user=Depends(current_user), db=Depends(get_db)):
    if user.email_verified:
        return {"message": "Email is already verified"}
    challenge = issue_code(db, user, request)
    account_event(db, "verification_requested", user=user, actor=user)
    db.commit()
    return registration_view(challenge, request)


@router.post("/auth/verification-code/resend", dependencies=[Depends(limit)])
def resend_code(body: ResendCode, request: Request, db=Depends(get_db)):
    row = db.scalar(select(VerificationCode).where(VerificationCode.challenge_hash == token_hash(body.challenge)))
    if row is None:
        return registration_view(secrets.token_urlsafe(32), request)
    user = db.get(User, row.user_id)
    if not user.active or user.email_verified:
        return registration_view(secrets.token_urlsafe(32), request)
    challenge = issue_code(db, user, request)
    account_event(db, "verification_requested", user=user)
    db.commit()
    return registration_view(challenge, request)


@router.post("/auth/verify-email", dependencies=[Depends(limit)])
def verify_email(body: CodeBody, request: Request, response: Response, db=Depends(get_db)):
    signed = current_user(request, db) if not body.challenge else None
    user = redeem_code(db, body.code, body.challenge, signed)
    account_event(db, "email_verified", user=user, actor=user)
    issue_session(db, user, request, response)
    return {"message": "Email verified. Continue to your account."}


@router.post("/auth/forgot-password", dependencies=[Depends(limit)])
def forgot(body: Email, request: Request, db=Depends(get_db)):
    if request.app.state.settings.mail_delivery == "disabled":
        raise HTTPException(503, "Password recovery requires configured account email delivery.")
    user = find_user(db, body.email)
    if user and user.active:
        try:
            send_token(db, user, "reset", request)
            account_event(db, "password_reset_requested", user=user)
            db.commit()
        except HTTPException:
            db.rollback()
            # Keep the response independent of account existence/delivery success.
    return {
        "message": "If an active account matches, a reset link has been requested.",
        "mail_delivery": request.app.state.settings.mail_delivery,
    }


@router.post("/auth/reset-password", dependencies=[Depends(limit)])
def reset(body: Reset, request: Request, response: Response, db=Depends(get_db)):
    user = consume_token(db, body.token, "reset")
    user.password_hash = hasher.hash(body.password)
    account_event(db, "password_reset_completed", user=user, actor=user)
    db.execute(delete(Session).where(Session.user_id == user.id))
    db.execute(delete(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == "reset"))
    db.commit()
    response.delete_cookie(
        COOKIE, path="/", secure=request.app.state.settings.cookie_secure, httponly=True, samesite="strict"
    )
    return {"message": "Password changed. Sign in with your new password."}


def verified(user=Depends(current_user)):
    if not user.email_verified:
        raise HTTPException(403, "Verify your email first")
    return user


@router.post("/organizations", status_code=201)
def create_organization(body: OrganizationCreate, user=Depends(verified), db=Depends(get_db)):
    if user.organization_id is not None:
        raise HTTPException(409, "Your account already belongs to an organization")
    organization = Organization(name=body.name)
    db.add(organization)
    db.flush()
    changed = db.execute(
        update(User)
        .where(User.id == user.id, User.organization_id.is_(None))
        .values(organization_id=organization.id, role=Role.OWNER)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Your account already belongs to an organization")
    create_starter_rubric(db, organization.id, user.id)
    account_event(db, "organization_created", user=user, actor=user, organization_id=organization.id)
    db.commit()
    db.refresh(user)
    return user_view(user)


@router.get("/account")
def account(request: Request, user=Depends(current_user)):
    settings = request.app.state.settings
    organization = user.organization
    access = user.email_verified and operational_access(organization, settings)
    pending = []
    if user.email_verified and not user.organization_id:
        invitations = db_invitations(request, user)
        pending = invitations
    return {
        **user_view(user),
        "operational_access": access,
        "access_expires_at": access_expiration(organization, settings) if access else None,
        "suspended": bool(organization and organization.suspended),
        "access_message": None if access or organization is None else INACTIVE_ACCESS_MESSAGE,
        "can_review": user.role in {Role.OWNER, Role.ADMIN, Role.MANAGER, Role.REVIEWER, Role.SUPERVISOR},
        "subscription_status": organization.subscription_status if organization else "inactive",
        "entitlement_source": organization.entitlement_source if organization else None,
        "entitlement_expires_at": organization.entitlement_expires_at if organization else None,
        "dev_activation_available": settings.dev_entitlements_enabled
        and settings.environment == "development"
        and user.role in {Role.OWNER, Role.ADMIN},
        "mail_delivery": settings.mail_delivery,
        "checkout_available": bool(
            user.role == Role.OWNER
            and request.app.state.settings.stripe_secret_key and request.app.state.settings.stripe_webhook_secret
        ),
        "onboarding_completed": organization.onboarding_completed if organization else False,
        "organization_suspended": bool(organization and organization.suspended),
        "pending_invitations": pending,
    }


def db_invitations(request, user):
    # Verified identity, never a public email lookup. Do not expose invitation bearer tokens.
    with request.app.state.db() as db:
        rows = db.execute(
            select(Invitation, Organization.name)
            .join(Organization, Organization.id == Invitation.organization_id)
            .join(User, User.id == Invitation.invited_by)
            .where(
                Invitation.email == user.email,
                Invitation.status == "pending",
                Invitation.expires_at > time.time(),
                User.active.is_(True),
                User.email_verified.is_(True),
                or_(
                    and_(Invitation.platform_issued.is_(False), User.role.in_([Role.OWNER, Role.ADMIN]),
                         User.organization_id == Invitation.organization_id),
                    and_(Invitation.platform_issued.is_(True), User.platform_authority.has(active=True)),
                ),
            )
            .order_by(Invitation.created_at.desc())
            .limit(25)
        ).all()
        return [{"id": i.id, "organization_name": name, "role": i.role, "expires_at": i.expires_at} for i, name in rows]


@router.post("/subscription/development-activation")
def activate(request: Request, user=Depends(verified), db=Depends(get_db)):
    settings = request.app.state.settings
    if settings.environment != "development" or not settings.dev_entitlements_enabled:
        raise HTTPException(404, "Development activation is unavailable")
    if not user.organization_id or user.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(403, "Only an organization owner or administrator can activate development access")
    expires = time.time() + 7 * 86400
    db.execute(
        update(Organization)
        .where(Organization.id == user.organization_id)
        .values(subscription_status="active", entitlement_source="development", entitlement_expires_at=expires)
    )
    db.add(
        EntitlementEvent(
            organization_id=user.organization_id, actor_id=user.id, action="development_activation", expires_at=expires
        )
    )
    db.commit()
    return {"message": "Development test access enabled for seven days. No payment was taken.", "expires_at": expires}


@router.get("/onboarding")
def onboarding(user=Depends(require("review")), db=Depends(get_db)):
    uploaded = db.scalar(select(Call.id).where(Call.organization_id == user.organization_id).limit(1)) is not None
    return {"completed": user.organization.onboarding_completed, "has_interactions": uploaded}


@router.post("/onboarding/complete")
def complete(body: CompleteSetup, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    if (
        not body.skip
        and db.scalar(select(Call.id).where(Call.organization_id == user.organization_id).limit(1)) is None
    ):
        raise HTTPException(409, "Upload a recording first, or choose to finish setup later")
    user.organization.onboarding_completed = True
    db.commit()
    return {"completed": True}
