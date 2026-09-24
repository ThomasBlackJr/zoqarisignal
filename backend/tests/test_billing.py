import hashlib
import hmac
import json
import time
from unittest.mock import Mock

import pytest
from sqlalchemy import select, func

from app.models import BillingAccount, BillingEvent, Organization, LEGACY_ORG
from app.services.billing import StripeBilling, PRICES
from app.services.entitlements import operational_access


@pytest.fixture
def billing(app):
    settings = app.state.settings
    settings.stripe_secret_key = "sk_test_fixture_only"
    settings.stripe_webhook_secret = "whsec_fixture_only"
    for plan in PRICES:
        for interval in PRICES[plan]:
            setattr(settings, f"stripe_price_{plan}_{interval}", f"price_{plan}_{interval}")
    adapter = Mock()
    adapter.verify_event.side_effect = StripeBilling(settings).verify_event
    adapter.customer.return_value = {"id": "cus_fixture"}
    adapter.price.return_value = price()
    adapter.checkout.return_value = {"id": "cs_fixture", "url": "https://checkout.stripe.com/fixture"}
    adapter.session.return_value = {"status": "open", "url": "https://checkout.stripe.com/fixture"}
    adapter.portal.return_value = {"url": "https://billing.stripe.com/fixture"}
    app.state.billing = adapter
    return adapter


def price(plan="starter", interval="month"):
    return {
        "id": f"price_{plan}_{interval}",
        "active": True,
        "livemode": False,
        "unit_amount": PRICES[plan][interval],
        "currency": "usd",
        "recurring": {"interval": interval, "interval_count": 1},
    }


def subscription(state="trialing"):
    return {
        "id": "sub_fixture",
        "customer": "cus_fixture",
        "metadata": {"signal_organization": LEGACY_ORG},
        "livemode": False,
        "status": state,
        "trial_start": time.time() - 20,
        "trial_end": time.time() + 86400,
        "items": {"data": [{"price": price(), "quantity": 1, "current_period_end": time.time() + 86400}]},
    }


def send(client, app, kind="customer.subscription.updated", eid="evt_fixture", obj=None):
    raw = json.dumps(
        {
            "id": eid,
            "livemode": False,
            "type": kind,
            "data": {"object": obj or {"id": "sub_fixture", "customer": "cus_fixture"}},
        }
    )
    stamp = str(int(time.time()))
    signature = hmac.new(
        app.state.settings.stripe_webhook_secret.encode(), (stamp + "." + raw).encode(), hashlib.sha256
    ).hexdigest()
    return client.post("/billing/webhook", content=raw, headers={"stripe-signature": f"t={stamp},v1={signature}"})


def test_checkout_idempotent_hosted_server_prices(signed_in, app, billing):
    body = {"plan": "starter", "interval": "month"}
    assert signed_in.post("/billing/checkout", json=body).status_code == 200
    assert signed_in.post("/billing/checkout", json=body).status_code == 200
    assert billing.checkout.call_count == 1
    params, key = billing.checkout.call_args.args
    assert params["subscription_data"]["trial_period_days"] == 14
    assert params["payment_method_collection"] == "always"
    assert params["line_items"] == [{"price": "price_starter_month", "quantity": 1}]
    assert params["customer"] == "cus_fixture" and key
    assert signed_in.post("/billing/checkout", json={**body, "price": "price_free"}).status_code == 422
    assert signed_in.post("/billing/checkout", json={"plan": "pro", "interval": "year"}).status_code == 409
    assert signed_in.post("/billing/portal").status_code == 200
    billing.portal.assert_called_once_with("cus_fixture")


def test_webhook_signature_duplicate_out_of_order_and_access(signed_in, app, billing):
    signed_in.post("/billing/checkout", json={"plan": "starter", "interval": "month"})
    assert signed_in.post("/billing/webhook", content="{}", headers={"stripe-signature": "bad"}).status_code == 400
    billing.subscription.return_value = subscription()
    assert send(signed_in, app).status_code == 200
    assert send(signed_in, app).json()["duplicate"]
    assert billing.subscription.call_count == 1
    for index, state in enumerate(["active", "past_due", "unpaid", "canceled", "active"]):
        billing.subscription.return_value = subscription(state)
        # Old payload claims trialing; authoritative retrieval must win.
        assert (
            send(
                signed_in,
                app,
                eid=f"evt_{index}",
                obj={"id": "sub_fixture", "customer": "cus_fixture", "status": "trialing"},
            ).status_code
            == 200
        )
        with app.state.db() as db:
            org = db.get(Organization, LEGACY_ORG)
            assert org.subscription_status == state
            assert operational_access(org, app.state.settings) == (state == "active")
    with app.state.db() as db:
        assert db.scalar(select(func.count()).select_from(BillingEvent)) == 6
        assert db.get(BillingAccount, LEGACY_ORG).trial_used


def test_binding_price_mode_and_failure_retry(signed_in, app, billing):
    signed_in.post("/billing/checkout", json={"plan": "starter", "interval": "month"})
    value = subscription()
    value["metadata"]["signal_organization"] = "another-tenant"
    billing.subscription.return_value = value
    assert send(signed_in, app).status_code == 503
    with app.state.db() as db:
        assert not db.get(BillingEvent, "evt_fixture")
    value = subscription("active")
    value["items"]["data"][0]["price"]["unit_amount"] = 1
    billing.subscription.return_value = value
    assert send(signed_in, app).status_code == 200
    with app.state.db() as db:
        assert not operational_access(db.get(Organization, LEGACY_ORG), app.state.settings)
    app.state.settings.environment = "production"
    with app.state.db() as db:
        org = db.get(Organization, LEGACY_ORG)
        org.subscription_status = "active"
        org.entitlement_expires_at = time.time() + 86400
        for source in ("development", "stripe_test"):
            org.entitlement_source = source
            assert not operational_access(org, app.state.settings)


def test_billing_permissions_and_unconfigured(client, app, billing):
    client.post("/auth/login", json={"email": "supervisor@example.test", "password": "test-password-only"})
    for method, path in [("get", "/billing"), ("post", "/billing/portal"), ("post", "/billing/checkout")]:
        response = getattr(client, method)(
            path, **({"json": {"plan": "starter", "interval": "month"}} if path.endswith("checkout") else {})
        )
        assert response.status_code == 403
    billing.customer.assert_not_called()


def test_checkout_uncertainty_reuses_durable_key(signed_in, app, billing):
    billing.checkout.side_effect = [
        TimeoutError("secret"),
        {"id": "cs_fixture", "url": "https://checkout.stripe.com/fixture"},
    ]
    body = {"plan": "starter", "interval": "month"}
    first = signed_in.post("/billing/checkout", json=body)
    assert first.status_code == 503 and "secret" not in first.text
    assert signed_in.post("/billing/checkout", json=body).status_code == 200
    assert billing.checkout.call_args_list[0] == billing.checkout.call_args_list[1]


def test_renewal_invoice_and_plan_change(signed_in, app, billing):
    signed_in.post("/billing/checkout", json={"plan": "starter", "interval": "month"})
    billing.subscription.return_value = subscription("active")
    billing.subscription.return_value["items"]["data"][0]["price"] = price("pro", "year")
    assert (
        send(
            signed_in,
            app,
            "invoice.paid",
            obj={"customer": "cus_fixture", "parent": {"subscription_details": {"subscription": "sub_fixture"}}},
        ).status_code
        == 200
    )
    with app.state.db() as db:
        account = db.get(BillingAccount, LEGACY_ORG)
        assert (account.plan, account.interval) == ("pro", "year")
