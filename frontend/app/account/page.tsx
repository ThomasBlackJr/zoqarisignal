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
  const [separateBusiness, setSeparateBusiness] = useState(false);
  const refresh = async () => {
    setAccount(await api<Account>("/account"));
  };
  useEffect(() => {
    api<Account>("/account")
      .then(setAccount)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!account?.organization_id || account.operational_access) return;
    const timer = setInterval(() => {
      api<Account>("/account")
        .then(setAccount)
        .catch(() => {});
    }, 15000);
    return () => clearInterval(timer);
  }, [account?.organization_id, account?.operational_access]);
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
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  const invites = account?.pending_invitations || [];
  const expiresAt = account?.access_expires_at !== undefined ? account.access_expires_at : account?.entitlement_expires_at;
  return (
    <AccountFrame>
      <div className="eyebrow">YOUR SIGNAL ACCOUNT</div>
      <h2>{account?.organization_name || "Welcome to Signal"}</h2>
      {error && <ErrorBox message={error} />}
      {message && <p role="status">{message}</p>}
      {!account ? (
        <>
          <Loading />
          <Link href="/login">Sign in</Link>
        </>
      ) : (
        <>
          <p className="muted">
            {account.name} · {account.email}
          </p>
          {account.is_platform_admin && (
            <Link className="button primary" href="/platform">
              Platform administration
            </Link>
          )}
          {!account.email_verified ? (
            <>
              <h3>Verify your email</h3>
              <p>
                Confirm your business email before joining or creating an
                organization.
              </p>
              <Link className="button primary" href="/verify-email">
                Enter verification code
              </Link>
              <button
                className="button secondary"
                disabled={pending}
                onClick={() => act("/auth/verification")}
              >
                Send verification code
              </button>
            </>
          ) : !account.organization_id ? (
            <>
              {invites.length > 0 && (
                <section aria-label="Your invitations">
                  <h3>You have an invitation</h3>
                  <p>
                    Join your existing team. You do not need to create another
                    organization.
                  </p>
                  {invites.map((i) => (
                    <div key={i.id} className="notice">
                      <strong>{i.organization_name}</strong>
                      <p>Invited role: {i.role}</p>
                      <button
                        className="button primary"
                        disabled={pending}
                        onClick={() => act(`/invitations/${i.id}/accept`)}
                      >
                        Join {i.organization_name}
                      </button>
                    </div>
                  ))}
                  <button
                    className="button secondary"
                    onClick={() => setSeparateBusiness(!separateBusiness)}
                  >
                    Create a separate business instead
                  </button>
                </section>
              )}
              {(invites.length === 0 || separateBusiness) && (
                <>
                  <h3>Create your business workspace</h3>
                  <p>
                    You will become its Owner. If your team invited you, use
                    that invitation to join its existing workspace. You can keep your account without creating an organization.
                  </p>
                  <form
                    className="account-form"
                    method="post"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void act("/organizations", {
                        name: new FormData(e.currentTarget).get("name"),
                      });
                    }}
                  >
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
              )}
            </>
          ) : (
            <>
              <h3>Signal Access</h3>
              <p>
                {account.organization_suspended
                  ? "Organization access is paused. Contact your administrator."
                  : account.operational_access
                    ? "Your organization has Beta Access to call analysis."
                    : account.access_message || "Your organization does not currently have Beta Access to call analysis. Contact your administrator."}
              </p>
              <p>
                Your account remains active. You can use the normal Signal
                dashboard.
              </p>
              {expiresAt && <p>Expiration: {date(expiresAt)}</p>}
              {account.operational_access &&
                !expiresAt && <p>Expiration: Never</p>}
              {!account.can_review && (
                <p>
                  Your role does not allow call upload or organization-wide
                  reviews.
                </p>
              )}
              <Link className="button primary" href="/">
                Open workspace
              </Link>
              <p>
                <Link href="/onboarding">{account.onboarding_completed ? "Review tutorial" : "Tutorial (optional)"}</Link>
              </p>
              <button
                className="button secondary"
                disabled={pending}
                onClick={() => void refresh().catch((e) => setError(e.message))}
              >
                Check access again
              </button>
              {account.role === "OWNER" && !account.suspended && <Billing />}
              {account.dev_activation_available && (
                <div className="development-note">
                  <strong>DEVELOPMENT TEST ACCESS</strong>
                  <p>
                    Seven days of local testing only. This does not approve a
                    production pilot.
                  </p>
                  <button
                    className="button secondary"
                    disabled={pending}
                    onClick={() => act("/subscription/development-activation")}
                  >
                    Activate development access
                  </button>
                </div>
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
