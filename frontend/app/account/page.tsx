"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Account, api, date } from "@/lib/api";
import { Billing } from "@/components/billing";
import { AccountFrame } from "@/components/account-frame";
import { ErrorBox, Loading } from "@/components/ui";

export default function AccountPage() {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    api<Account>("/account")
      .then(setAccount)
      .catch((e) => setError(e.message));
  }, []);
  async function act(path: string, body?: object) {
    setError("");
    setMessage("");
    setPending(true);
    try {
      const result = await api<{ message?: string; challenge?: string }>(path, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (result.challenge) {
        router.replace(
          `/verify-email#challenge=${encodeURIComponent(result.challenge)}`,
        );
        return;
      }
      setMessage(result?.message || "");
      setAccount(await api<Account>("/account"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  async function organization(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await act("/organizations", {
      name: new FormData(event.currentTarget).get("name"),
    });
  }
  return (
    <AccountFrame>
      <div className="eyebrow">ACCOUNT & ACCESS</div>
      <h2>{account?.organization_name || "Welcome to Signal"}</h2>
      {error && <ErrorBox message={error} />}
      {message && <p role="status">{message}</p>}
      {!account ? (
        <Loading />
      ) : (
        <>
          <p className="muted">
            {account.name} · {account.email}
          </p>
          <ol className="setup-progress" aria-label="Account setup progress">
            <li className={account.email_verified ? "done" : ""}>
              Verify email
            </li>
            <li className={account.organization_id ? "done" : ""}>
              Create business
            </li>
            <li className={account.operational_access ? "done" : ""}>
              Activate access
            </li>
          </ol>
          {!account.email_verified ? (
            <>
              <h3>Verify your business email</h3>
              <p>
                Verification is required before creating or accessing a business
                workspace.
              </p>
              {account.mail_delivery === "local" ? (
                <p className="development-note">
                  LOCAL DEVELOPMENT · No email was sent. Open the verification
                  code in the newest message in backend/data/mail-outbox. Treat
                  these files like passwords.
                </p>
              ) : (
                <p>
                  Check your email for a six-digit verification code. If
                  delivery is unavailable, contact the administrator.
                </p>
              )}
              <Link href="/verify-email" className="button primary">
                Enter verification code
              </Link>
              <button
                className="button primary"
                disabled={pending}
                onClick={() => act("/auth/verification")}
              >
                Resend verification
              </button>
              <button
                className="button secondary"
                disabled={pending}
                onClick={async () => {
                  setError("");
                  try {
                    setAccount(await api<Account>("/account"));
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                I have verified my email
              </button>
            </>
          ) : !account.organization_id ? (
            <>
              <h3>Create your business workspace</h3>
              <p>
                You will become its Owner. Your data and scorecards belong to
                this organization.
              </p>
              <form className="account-form" onSubmit={organization}>
                <label htmlFor="business-name">Business name</label>
                <input
                  id="business-name"
                  name="name"
                  maxLength={120}
                  required
                />
                <button className="button primary" disabled={pending}>
                  Create organization
                </button>
              </form>
            </>
          ) : (
            <>
              <h3>
                {account.operational_access
                  ? "Your workspace is ready"
                  : "Operational access required"}
              </h3>
              <dl className="access-summary">
                <div>
                  <dt>Access state</dt>
                  <dd>{account.subscription_status}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>
                    {account.entitlement_source === "development"
                      ? "Development test entitlement"
                      : account.entitlement_source?.startsWith("stripe_")
                        ? "Stripe subscription"
                        : "No subscription"}
                  </dd>
                </div>
                {account.entitlement_expires_at && (
                  <div>
                    <dt>Expires</dt>
                    <dd>{date(account.entitlement_expires_at)}</dd>
                  </div>
                )}
              </dl>
              {["OWNER", "ADMIN"].includes(account.role) ? (
                <Billing />
              ) : (
                <p>
                  Contact your organization Owner or Admin to manage billing.
                </p>
              )}
              {account.dev_activation_available && (
                <div className="development-note">
                  <strong>DEVELOPMENT TEST ACCESS</strong>
                  <p>
                    Enable seven days of local testing. This is not a paid
                    subscription. Configured live AI providers may still incur
                    provider charges.
                  </p>
                  <button
                    className="button secondary"
                    disabled={pending}
                    onClick={() => act("/subscription/development-activation")}
                  >
                    {pending
                      ? "Activating…"
                      : account.operational_access
                        ? "Renew development access"
                        : "Activate development access"}
                  </button>
                </div>
              )}
              {!account.dev_activation_available &&
                !account.operational_access && (
                  <p>
                    Ask the organization owner or local administrator to
                    configure access. Development activation is disabled in
                    production.
                  </p>
                )}
              {account.operational_access && account.can_review && (
                <Link
                  className="button primary"
                  href={account.onboarding_completed ? "/" : "/onboarding"}
                >
                  {account.onboarding_completed
                    ? "Open workspace"
                    : "Continue setup"}
                </Link>
              )}
              {account.operational_access && !account.can_review && (
                <p>
                  Your role does not have workspace review access. Ask your
                  organization owner for help.
                </p>
              )}
            </>
          )}
          <div className="account-links">
            <Link href="/forgot-password">Reset password</Link>
            <button
              className="button secondary"
              disabled={pending}
              onClick={async () => {
                try {
                  await api("/auth/logout", { method: "POST" });
                  router.replace("/login");
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Log out
            </button>
          </div>
        </>
      )}
    </AccountFrame>
  );
}
