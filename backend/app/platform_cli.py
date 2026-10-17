"""Trusted operator provisioning only. Never creates credentials or customer membership."""

import argparse

from .auth import find_user
from .config import DatabaseSettings
from .db import make_database
from .models import PlatformAdministrator, PlatformEvent
from .models import Session
from sqlalchemy import delete


def set_authority(db, email, active, reason, revoke_sessions=False):
    user = find_user(db, email)
    if not user or not user.active or not user.email_verified:
        raise ValueError("An existing active verified account is required")
    authority = db.get(PlatformAdministrator, user.id)
    if authority is None:
        authority = PlatformAdministrator(user_id=user.id)
        db.add(authority)
    authority.active = active
    if revoke_sessions:
        db.execute(delete(Session).where(Session.user_id == user.id))
    db.add(
        PlatformEvent(
            actor_id=user.id,
            action="platform.provision" if active else "platform.revoke",
            reason=reason,
            details={"channel": "trusted_local_cli", "target_user_id": user.id},
        )
    )
    db.commit()


def main():
    parser = argparse.ArgumentParser(description="Trusted local operator: grant/revoke platform authority")
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true")
    parser.add_argument("--reason", default="Trusted local operator provisioning")
    args = parser.parse_args()
    if not args.reason.strip() or len(args.reason) > 500:
        parser.error("A nonblank reason of at most 500 characters is required")
    engine, factory = make_database(DatabaseSettings().database_url)
    try:
        with factory() as db:
            set_authority(db, args.email, not args.revoke, args.reason.strip(), revoke_sessions=True)
    finally:
        engine.dispose()
    print("Platform access updated; existing sessions revoked. Sign in again.")


if __name__ == "__main__":
    main()
