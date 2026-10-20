"""One-time trusted bootstrap/revoke of separate platform authority; never creates users."""

import argparse
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from .config import DatabaseSettings
from .db import make_database
from .models import PlatformAdministrator, PlatformEvent, User, Session
from .services.account_audit import account_event


def set_authority(db, email, *, revoke=False, reason):
    if not reason.strip() or len(reason.strip()) > 500:
        raise ValueError("A nonblank reason of at most 500 characters is required")
    db.execute(update(User).where(User.email == email.strip().lower()).values(active=User.active))
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or (not revoke and (not user.active or not user.email_verified)):
        raise ValueError("Grant requires an existing active verified account")
    authority = db.get(PlatformAdministrator, user.id)
    if authority is None:
        if revoke:
            raise ValueError("Account has no platform authority")
        authority = PlatformAdministrator(user_id=user.id)
        db.add(authority)
    authority.active = not revoke
    from sqlalchemy import delete

    db.execute(delete(Session).where(Session.user_id == user.id))
    account_event(
        db, "platform_revoked" if revoke else "platform_granted", user=user, actor=user, reason=reason.strip()
    )
    db.add(
        PlatformEvent(
            actor_id=user.id,
            action="platform.revoke" if revoke else "platform.provision",
            reason=reason.strip(),
            details={"channel": "trusted_local_cli", "user_id": user.id},
        )
    )
    db.commit()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trusted bootstrap only: grant/revoke separate platform authority")
    parser.add_argument("email")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args(argv)
    engine = None
    try:
        engine, factory = make_database(DatabaseSettings().database_url)
        with factory() as db:
            set_authority(db, args.email, revoke=args.revoke, reason=args.reason)
    except (ValueError, SQLAlchemyError):
        parser.exit(
            1, "Platform operation failed. Check the existing verified account, database and migration privately.\n"
        )
    finally:
        if engine:
            engine.dispose()
    print("Platform authority updated; sessions revoked. Sign in again.")


if __name__ == "__main__":
    main()
