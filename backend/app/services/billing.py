"""Stripe adapter. Hosted payment pages only; no card data enters Signal."""

import stripe

PRICES = {
    "starter": {"month": 7500, "year": 75000},
    "business": {"month": 20000, "year": 200000},
    "pro": {"month": 40000, "year": 400000},
}


def configured(settings):
    return bool(
        settings.stripe_secret_key
        and settings.stripe_webhook_secret
        and all(getattr(settings, f"stripe_price_{plan}_{interval}") for plan in PRICES for interval in PRICES[plan])
    )


class StripeBilling:
    def __init__(self, settings):
        self.settings = settings
        self.client = (
            stripe.StripeClient(settings.stripe_secret_key, max_network_retries=2)
            if settings.stripe_secret_key
            else None
        )

    def verify_event(self, payload, signature):
        return stripe.Webhook.construct_event(payload, signature, self.settings.stripe_webhook_secret, tolerance=300)

    def price(self, price_id):
        return self.client.v1.prices.retrieve(price_id)

    def customer(self, org_id):
        return self.client.v1.customers.create(
            {"metadata": {"signal_organization": org_id}}, options={"idempotency_key": "signal-customer-" + org_id}
        )

    def checkout(self, params, key):
        return self.client.v1.checkout.sessions.create(params, options={"idempotency_key": key})

    def session(self, session_id):
        return self.client.v1.checkout.sessions.retrieve(session_id)

    def subscription(self, subscription_id):
        return self.client.v1.subscriptions.retrieve(subscription_id)

    def portal(self, customer_id):
        return self.client.v1.billing_portal.sessions.create(
            {"customer": customer_id, "return_url": self.settings.frontend_origin + "/account"}
        )


def matching_price(price, settings):
    for plan, intervals in PRICES.items():
        for interval, amount in intervals.items():
            if (
                price.get("id") == getattr(settings, f"stripe_price_{plan}_{interval}")
                and price.get("currency") == "usd"
                and price.get("unit_amount") == amount
                and price.get("recurring", {}).get("interval") == interval
                and price.get("recurring", {}).get("interval_count") == 1
            ):
                return plan, interval
    return None
