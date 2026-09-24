import hashlib
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .models import Role, Session, User
from .services.entitlements import assert_account_access

hasher = PasswordHasher()
dummy_hash = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "drive_session"
PERMISSIONS = {
    Role.OWNER: {
        "review",
        "manage_users",
        "manage_rubrics",
        "manage_employees",
        "assign_interactions",
        "delete_records",
    },
    Role.ADMIN: {
        "review",
        "manage_users",
        "manage_rubrics",
        "manage_employees",
        "assign_interactions",
        "delete_records",
    },
    Role.MANAGER: {"review", "manage_employees", "assign_interactions"},
    Role.REVIEWER: {"review"},
    Role.SUPERVISOR: {"review"},
    Role.EMPLOYEE: set(),
}


def token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def verify(password: str, password_hash: str):
    try:
        return hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def get_db(request: Request):
    with request.app.state.db() as db:
        yield db


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE)
    session = db.get(Session, token_hash(token)) if token else None
    if not session or session.expires_at <= time.time() or not session.user.active:
        raise HTTPException(401, "Please sign in to Signal")
    return session.user


def require(permission: str):
    def check(request: Request, user: User = Depends(current_user)):
        assert_account_access(user, request.app.state.settings)
        if permission not in PERMISSIONS.get(user.role, set()):
            raise HTTPException(403, "Your role does not permit this action")
        return user

    return check


def user_view(user):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "organization_id": user.organization_id,
        "organization_name": user.organization.name if user.organization else None,
        "email_verified": user.email_verified,
    }


def find_user(db, email):
    return db.scalar(select(User).where(User.email == email.strip().lower()))
