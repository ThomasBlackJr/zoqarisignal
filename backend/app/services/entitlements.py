"""One access decision shared by authenticated APIs and the processing worker."""

import math
import time
from fastapi import HTTPException
from ..models import Organization


INACTIVE_ACCESS_MESSAGE = "Your organization's access is currently inactive. Please contact your organization owner."


def beta_active(organization):
    beta = organization.beta_access
    return bool(
        beta
        and beta.active
        and (beta.expires_at is None or (math.isfinite(beta.expires_at) and beta.expires_at > time.time()))
    )


def operational_access(organization, settings):
    return bool(
        organization
        and not organization.suspended
        and (beta_active(organization) or entitlement_access(organization, settings))
    )


def access_expiration(organization, settings):
    if not operational_access(organization, settings):
        return None
    expirations = []
    if beta_active(organization):
        expirations.append(organization.beta_access.expires_at)
    if entitlement_access(organization, settings):
        expirations.append(organization.entitlement_expires_at)
    return None if None in expirations else max(expirations)


def entitlement_access(organization, settings):
    if organization.subscription_status not in {"active", "trialing"}:
        return False
    if organization.entitlement_source == "pilot":
        expires = organization.entitlement_expires_at
        return organization.subscription_status == "active" and (
            expires is None or (math.isfinite(expires) and expires > time.time())
        )
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


def assert_workspace_access(user):
    if not user.email_verified:
        raise HTTPException(403, "Verify your email before opening the workspace")
    if not user.organization_id:
        raise HTTPException(403, "Create your organization before opening the workspace")
    if user.organization.suspended:
        raise HTTPException(403, INACTIVE_ACCESS_MESSAGE)


def assert_account_access(user, settings):
    """Product access: explicit organization entitlement in addition to workspace identity."""
    assert_workspace_access(user)
    if not operational_access(user.organization, settings):
        raise HTTPException(403, "Beta access required for call upload and AI analysis. Contact your administrator.")
