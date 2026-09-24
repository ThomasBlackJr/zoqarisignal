"""Billing management deliberately remains accessible when workspace entitlement lapses."""

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update

from .auth import current_user, get_db
from .logging import event
from .models import BillingAccount, BillingEvent, Organization, Role, identifier
from .schemas import StrictModel
from .services.billing import PRICES, configured, matching_price
from .services.entitlements import operational_access

router = APIRouter(prefix="/billing")


def manager(user=Depends(current_user)):
    if not user.email_verified or not user.organization_id or user.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(403, "A verified organization Owner or Admin must manage billing")
    return user


def available(request):
    if not configured(request.app.state.settings):
        raise HTTPException(503, "Billing is not configured yet. Contact Zoqari for beta access.")
    return request.app.state.billing


def lock_account(db, org_id):
    db.execute(update(Organization).where(Organization.id == org_id).values(name=Organization.name))
    account = db.get(BillingAccount, org_id, populate_existing=True)
    if not account:
        account = BillingAccount(organization_id=org_id)
        db.add(account)
        db.flush()
    return account


@router.get("")
def status(request: Request, user=Depends(manager), db=Depends(get_db)):
    account = db.get(BillingAccount, user.organization_id)
    return {
        "configured": configured(request.app.state.settings),
        "mode": request.app.state.settings.stripe_mode,
        "plans": PRICES,
        "status": user.organization.subscription_status,
        "operational_access": operational_access(user.organization, request.app.state.settings),
        "plan": account.plan if account else None,
        "interval": account.interval if account else None,
        "trial_available": not account or not account.trial_used,
        "portal_available": bool(account and account.customer_id),
        "synced_at": account.synced_at if account else None,
    }


class Choice(StrictModel):
    plan: Literal["starter", "business", "pro"]
    interval: Literal["month", "year"]


@router.post("/checkout")
def checkout(body: Choice, request: Request, user=Depends(manager), db=Depends(get_db)):
    billing = available(request)
    settings = request.app.state.settings
    account = lock_account(db, user.organization_id)
    if account.subscription_id and user.organization.subscription_status not in {
        "canceled",
        "incomplete_expired",
        "inactive",
    }:
        raise HTTPException(409, "Manage your existing subscription in the billing portal")
    selection = body.plan + ":" + body.interval
    try:
        if account.checkout_id:
            existing = billing.session(account.checkout_id)
            if existing.get("status") == "open":
                if selection != account.checkout_plan:
                    raise HTTPException(
                        409,
                        "An existing Checkout is open. Complete it or wait for its 30-minute expiry before changing plans.",
                    )
                return {"url": existing["url"]}
            if existing.get("status") == "complete" and not account.subscription_id:
                raise HTTPException(
                    409, "Checkout completed; waiting for confirmed subscription state. Refresh shortly."
                )
            account.checkout_id = None
            account.checkout_key = None
        if account.checkout_key and account.checkout_expires <= time.time():
            # Never replay a key beyond Stripe's retention horizon after an uncertain request.
            raise HTTPException(
                409,
                "An interrupted checkout needs reconciliation. Contact support before starting another subscription.",
            )
        price_id = getattr(settings, f"stripe_price_{body.plan}_{body.interval}")
        price = billing.price(price_id)
        if (
            not price.get("active")
            or matching_price(price, settings) != (body.plan, body.interval)
            or bool(price.get("livemode")) != (settings.stripe_mode == "live")
        ):
            raise HTTPException(503, "The configured Stripe price does not match this plan. Contact support.")
        if not account.customer_id:
            account.customer_id = billing.customer(user.organization_id)["id"]
        if not account.checkout_key:
            account.checkout_key = identifier()
            account.checkout_plan = selection
            account.checkout_expires = int(time.time()) + 1800
        elif account.checkout_plan != selection:
            raise HTTPException(409, "Retry the original checkout plan before changing plans")
        # Durable key BEFORE external mutation: uncertain failures reuse the exact request.
        db.commit()
        account = lock_account(db, user.organization_id)
        sub = {"metadata": {"signal_organization": user.organization_id}}
        if not account.trial_used:
            sub["trial_period_days"] = 14
            sub["trial_settings"] = {"end_behavior": {"missing_payment_method": "cancel"}}
        result = billing.checkout(
            {
                "mode": "subscription",
                "customer": account.customer_id,
                "client_reference_id": user.organization_id,
                "line_items": [{"price": price_id, "quantity": 1}],
                "payment_method_collection": "always",
                "payment_method_types": ["card"],
                "subscription_data": sub,
                "success_url": settings.frontend_origin + "/account?checkout=complete",
                "cancel_url": settings.frontend_origin + "/account?checkout=canceled",
                "expires_at": int(account.checkout_expires),
            },
            account.checkout_key,
        )
        account.checkout_id = result["id"]
        db.commit()
        return {"url": result["url"]}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        event("billing_checkout_failed", error_type=type(exc).__name__)
        raise HTTPException(503, "Checkout is temporarily unavailable. Retry the same plan shortly.") from None


@router.post("/portal")
def portal(request: Request, user=Depends(manager), db=Depends(get_db)):
    billing = available(request)
    account = db.get(BillingAccount, user.organization_id)
    if not account or not account.customer_id:
        raise HTTPException(409, "Start a subscription before opening the billing portal")
    try:
        return {"url": billing.portal(account.customer_id)["url"]}
    except Exception as exc:
        event("billing_portal_failed", error_type=type(exc).__name__)
        raise HTTPException(503, "Billing portal is temporarily unavailable") from None


def synchronize(db, account, subscription, settings):
    # Retrieved live from Stripe UNDER the organization lock, never trust event arrival order.
    if (
        subscription.get("customer") != account.customer_id
        or subscription.get("metadata", {}).get("signal_organization") != account.organization_id
    ):
        raise ValueError("subscription_binding")
    if bool(subscription.get("livemode")) != (settings.stripe_mode == "live"):
        raise ValueError("subscription_mode")
    if account.subscription_id and account.subscription_id != subscription["id"]:
        raise ValueError("subscription_conflict")
    org = db.get(Organization, account.organization_id, populate_existing=True)
    items = subscription.get("items", {}).get("data", [])
    selected = (
        matching_price(items[0].get("price", {}), settings)
        if len(items) == 1 and items[0].get("quantity") == 1
        else None
    )
    account.subscription_id = subscription["id"]
    account.livemode = bool(subscription.get("livemode"))
    account.trial_used = account.trial_used or bool(subscription.get("trial_start"))
    account.synced_at = time.time()
    account.plan, account.interval = selected or (None, None)
    state = subscription.get("status", "inactive")
    org.entitlement_source = "stripe_live" if account.livemode else "stripe_test"
    org.subscription_status = state if selected else "inactive"
    period = (
        subscription.get("trial_end")
        if state == "trialing"
        else (items[0].get("current_period_end") if items else None)
    )
    period = period or subscription.get("current_period_end")
    org.entitlement_expires_at = float(period) if selected and state in {"active", "trialing"} and period else None


EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
}


@router.post("/webhook")
async def webhook(request: Request, db=Depends(get_db)):
    billing = available(request)
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 1048576:
            raise HTTPException(413, "Webhook too large")
    try:
        incoming = billing.verify_event(bytes(payload), request.headers.get("stripe-signature", ""))
    except Exception:
        raise HTTPException(400, "Invalid webhook signature") from None
    if bool(incoming.get("livemode")) != (request.app.state.settings.stripe_mode == "live"):
        raise HTTPException(400, "Unexpected billing mode")
    kind = incoming.get("type")
    if kind not in EVENTS:
        return {"received": True}
    try:
        obj = incoming["data"]["object"]
        customer_id = obj.get("customer")
        account = (
            db.scalar(select(BillingAccount).where(BillingAccount.customer_id == customer_id)) if customer_id else None
        )
        if not account:
            # A shared Stripe account may contain unrelated customers.
            return {"received": True}
        account = lock_account(db, account.organization_id)
        if db.get(BillingEvent, incoming["id"]):
            return {"received": True, "duplicate": True}
        subscription_id = obj.get("id") if kind.startswith("customer.subscription.") else obj.get("subscription")
        if kind.startswith("invoice."):
            subscription_id = subscription_id or obj.get("parent", {}).get("subscription_details", {}).get(
                "subscription"
            )
        if not subscription_id:
            return {"received": True}
        if account.subscription_id and subscription_id != account.subscription_id:
            # Ignore delayed old-subscription events. New subscriptions must originate from our Checkout.
            if kind != "checkout.session.completed" or obj.get("id") != account.checkout_id:
                return {"received": True}
            old = billing.subscription(account.subscription_id)
            if old.get("status") not in {"canceled", "incomplete_expired"}:
                raise ValueError("multiple_subscriptions")
            account.subscription_id = None
        synchronize(db, account, billing.subscription(subscription_id), request.app.state.settings)
        db.add(BillingEvent(id=incoming["id"], event_type=kind))
        db.commit()
        event("billing_synchronized", organization_id=account.organization_id)
        return {"received": True}
    except Exception as exc:
        db.rollback()
        event("billing_webhook_failed", error_type=type(exc).__name__)
        raise HTTPException(503, "Billing synchronization unavailable; retry this event") from None
