"""Shared audited pilot mutation; trusted CLI or explicitly checked platform authority."""

import math
import time
from sqlalchemy import select, update
from ..models import EntitlementEvent, Organization, PlatformAdministrator, Role, User
from .account_audit import account_event


def change_pilot(
    db, organization_id, confirm_name, actor_email, reason, *, revoke=False, expires_at=None, platform_actor=None
):
    """Caller must hold trusted database/operator access; actor is audit attribution, not CLI authentication."""
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValueError("A nonblank audit reason of at most 500 characters is required")
    if expires_at is not None and (not math.isfinite(expires_at) or expires_at <= time.time()):
        raise ValueError("Expiry must be in the future")
    if revoke and expires_at is not None:
        raise ValueError("Revocation does not accept an expiry")
    # Serialize grant/revoke with other changes to the same organization.
    db.execute(update(Organization).where(Organization.id == organization_id).values(id=Organization.id))
    organization = db.get(Organization, organization_id, populate_existing=True)
    if organization is None or organization.name != confirm_name:
        raise ValueError("Organization ID and exact confirmation name must match")
    actor = platform_actor or db.scalar(select(User).where(User.email == actor_email.strip().lower()))
    authority = db.get(PlatformAdministrator, actor.id) if platform_actor else None
    platform_allowed = bool(platform_actor and authority and authority.active and actor.active and actor.email_verified)
    if (
        actor is None
        or (platform_actor is not None and not platform_allowed)
        or (
            platform_actor is None
            and (
                actor.organization_id != organization.id
                or actor.role not in {Role.OWNER, Role.ADMIN}
                or (not revoke and (not actor.active or not actor.email_verified))
            )
        )
    ):
        raise ValueError("Audit actor must be this organization's Owner/Admin; grants require active verified accounts")
    if organization.entitlement_source not in {None, "development", "pilot"}:
        raise ValueError("Refusing to replace another entitlement source")
    if revoke:
        if organization.entitlement_source != "pilot":
            raise ValueError("This organization has no pilot entitlement to revoke")
        organization.subscription_status = "inactive"
    else:
        organization.entitlement_source = "pilot"
        organization.subscription_status = "active"
        organization.entitlement_expires_at = expires_at
    db.add(
        EntitlementEvent(
            organization_id=organization.id,
            actor_id=actor.id,
            action="pilot_revoke" if revoke else "pilot_grant",
            expires_at=organization.entitlement_expires_at,
            reason=reason,
        )
    )
    account_event(
        db, "pilot_revoked" if revoke else "pilot_granted", actor=actor, organization_id=organization.id, reason=reason
    )
    db.commit()
