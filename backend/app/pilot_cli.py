"""Trusted server operator only: audited organization pilot grants, never user/role creation."""

import argparse
from datetime import datetime, timezone
import math
import time

from sqlalchemy.exc import SQLAlchemyError

from .config import DatabaseSettings
from .db import make_database
from .services.pilot import change_pilot


def expiry(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        result = parsed.astimezone(timezone.utc).timestamp()
        if not math.isfinite(result) or result <= time.time():
            raise ValueError()
        return result
    except (ValueError, OverflowError):
        raise argparse.ArgumentTypeError(
            "Expiry must be a future ISO-8601 date/time with timezone, e.g. 2026-11-19T23:59:59Z"
        ) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trusted server operator: grant/revoke free pilot access")
    parser.add_argument("action", choices=["grant", "revoke"])
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--confirm-name", required=True, help="Exact existing organization name")
    parser.add_argument(
        "--actor-email",
        required=True,
        help="Organization Owner/Admin for audit attribution; grants require active verification",
    )
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "--expires-at", type=expiry, help="Optional future ISO-8601 timestamp with timezone; omit for no expiry"
    )
    args = parser.parse_args(argv)
    if args.action == "revoke" and args.expires_at is not None:
        parser.error("--expires-at applies only to grant")
    engine = None
    try:
        # No application import, mail provider, AI provider, worker or migration.
        settings = DatabaseSettings()
        engine, factory = make_database(settings.database_url)
        with factory() as db:
            change_pilot(
                db,
                args.organization_id,
                args.confirm_name,
                args.actor_email,
                args.reason,
                revoke=args.action == "revoke",
                expires_at=args.expires_at,
            )
    except ValueError as exc:
        # Configuration errors may contain rejected credentials; only our fixed service errors are public.
        if engine is None:
            parser.exit(1, "Pilot operation failed. Check database/environment configuration privately.\n")
        parser.exit(1, f"{exc}\n")
    except SQLAlchemyError:
        parser.exit(1, "Pilot operation failed. Check database availability and migration status privately.\n")
    finally:
        if engine is not None:
            engine.dispose()
    print("Pilot access granted." if args.action == "grant" else "Pilot access revoked.")


if __name__ == "__main__":
    main()
