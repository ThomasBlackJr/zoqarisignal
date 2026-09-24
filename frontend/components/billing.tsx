"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
type BillingState = {
  configured: boolean;
  mode: string;
  plans: Record<string, Record<string, number>>;
  status: string;
  plan: string | null;
  interval: string | null;
  trial_available: boolean;
  portal_available: boolean;
};
export function Billing() {
  const [data, setData] = useState<BillingState | null>(null);
  const [interval, setInterval] = useState("month");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<BillingState>("/billing")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  async function open(path: string, plan?: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ url: string }>(path, {
        method: "POST",
        ...(plan ? { body: JSON.stringify({ plan, interval }) } : {}),
      });
      window.location.assign(result.url);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <section aria-label="Subscription billing">
      <h3>Subscription & billing</h3>
      {error && <ErrorBox message={error} />}
      {!data ? (
        <p>Loading billing�</p>
      ) : !data.configured ? (
        <p>
          Private beta � Online billing is awaiting configuration. Contact
          Zoqari for availability.
        </p>
      ) : (
        <>
          {data.mode === "test" && (
            <p className="development-note">
              STRIPE TEST MODE � Use test payment details only. This does not
              create a live paid subscription.
            </p>
          )}
          <p>
            {data.plan
              ? `${data.plan} � ${data.interval} � ${data.status}`
              : "Choose a plan to start your workspace."}
          </p>
          <p>
            {data.trial_available
              ? "14-day free trial. A payment method is required. Your selected subscription starts billing after the trial unless canceled in the billing portal."
              : "Your organization has already used its trial. A new subscription is billed without another free trial."}
          </p>
          <label>
            Billing interval{" "}
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
            >
              <option value="month">Monthly</option>
              <option value="year">Annual � two months free</option>
            </select>
          </label>
          <div className="account-form">
            {Object.entries(data.plans).map(([plan, amounts]) => (
              <button
                className="button secondary"
                key={plan}
                disabled={busy}
                onClick={() => open("/billing/checkout", plan)}
              >
                {plan[0].toUpperCase() + plan.slice(1)} � $
                {(amounts[interval] / 100).toLocaleString()} / {interval}
              </button>
            ))}
          </div>
          <p>Enterprise � Contact Zoqari for a custom proposal.</p>
          {data.portal_available && (
            <button
              className="button primary"
              disabled={busy}
              onClick={() => open("/billing/portal")}
            >
              Manage billing / cancel subscription
            </button>
          )}
          <p className="muted">
            Checkout redirects do not activate access. Refresh this page after
            Stripe confirms your subscription. Saved records remain stored if
            access expires.
          </p>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => window.location.reload()}
          >
            Refresh subscription status
          </button>
        </>
      )}
    </section>
  );
}
