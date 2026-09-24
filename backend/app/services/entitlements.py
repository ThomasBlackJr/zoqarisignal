"""One access decision shared by authenticated APIs and the paid processing worker."""

import time
from fastapi import HTTPException
from ..models import Organization


def operational_access(organization, settings):
    if organization is None or organization.subscription_status not in {"active", "trialing"}:
        return False
    if not organization.entitlement_expires_at or organization.entitlement_expires_at <= time.time():
        return False
    if organization.entitlement_source == "stripe_live":
        return (
            settings.environment == "production"
            and settings.stripe_mode == "live"
            and bool(settings.stripe_secret_key and settings.stripe_webhook_secret)
        )
    if organization.entitlement_source == "stripe_test":
        return (
            settings.environment == "development"
            and settings.stripe_mode == "test"
            and bool(settings.stripe_secret_key and settings.stripe_webhook_secret)
        )
    # Unknown sources fail closed.
    return (
        organization.entitlement_source == "development"
        and settings.environment == "development"
        and settings.dev_entitlements_enabled
    )


def assert_worker_access(db, organization_id, settings):
    organization = db.get(Organization, organization_id, populate_existing=True)
    if not operational_access(organization, settings):
        raise EntitlementRequired()


class EntitlementRequired(Exception):
    pass


def assert_account_access(user, settings):
    if not user.email_verified:
        raise HTTPException(403, "Verify your email before opening the workspace")
    if not user.organization_id:
        raise HTTPException(403, "Create your organization before opening the workspace")
    if not operational_access(user.organization, settings):
        raise HTTPException(403, "An active subscription or enabled development entitlement is required")
