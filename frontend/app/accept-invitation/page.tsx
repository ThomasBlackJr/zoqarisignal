"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { Account, accountDestination, api } from "@/lib/api";
import { AccountFrame } from "@/components/account-frame";
import { ErrorBox } from "@/components/ui";
import { useHydrated } from "@/lib/use-hydrated";

const subscribe = (f: () => void) => {
  window.addEventListener("hashchange", f);
  return () => window.removeEventListener("hashchange", f);
};
export default function AcceptInvitation() {
  const hash = useSyncExternalStore(
    subscribe,
    () => window.location.hash,
    () => "",
  );
  const token = new URLSearchParams(hash.slice(1)).get("token") ?? "";
  const hydrated = useHydrated();
  const router = useRouter();
  const [invite, setInvite] = useState<{
    email: string;
    organization_name: string;
    role: string;
  } | null>(null);
  const [mode, setMode] = useState("new");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let alive = true;
    if (token)
      api<typeof invite>("/invitations/preview", {
        method: "POST",
        body: JSON.stringify({ token }),
      })
        .then((v) => {
          if (alive) setInvite(v);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    return () => {
      alive = false;
    };
  }, [token]);
  async function accept(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!invite) return;
    setSaving(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      if (mode === "new")
        await api("/invitations/register", {
          method: "POST",
          body: JSON.stringify({
            token,
            email: invite.email,
            name: form.get("name"),
            password: form.get("password"),
          }),
        });
      else {
        await api("/auth/login", {
          method: "POST",
          body: JSON.stringify({
            email: invite.email,
            password: form.get("password"),
          }),
        });
        await api("/invitations/accept", {
          method: "POST",
          body: JSON.stringify({ token }),
        });
      }
      window.history.replaceState(null, "", window.location.pathname);
      router.replace(accountDestination(await api<Account>("/account")));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <AccountFrame invitation>
      <div className="eyebrow">TEAM INVITATION</div>
      <h2>Join your organization</h2>
      <p>
        This joins the existing business. No new organization or subscription is
        created.
      </p>
      {error && <ErrorBox message={error} />}
      {invite ? (
        <>
          <p className="notice">
            <strong>{invite.organization_name}</strong>
            <br />
            {invite.email} · {invite.role}
          </p>
          <label>
            Account option
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="new">Create my account</option>
              <option value="existing">Sign in to accept</option>
            </select>
          </label>
          <form method="post" className="account-form" onSubmit={accept}>
            <fieldset disabled={!hydrated || saving}>
              {mode === "new" && (
                <label>
                  Your name
                  <input
                    name="name"
                    required
                    maxLength={100}
                    autoComplete="name"
                  />
                </label>
              )}
              <label>
                {mode === "new" ? "Choose password" : "Existing password"}
                <input
                  name="password"
                  type="password"
                  required
                  minLength={mode === "new" ? 12 : 1}
                  maxLength={256}
                  autoComplete={
                    mode === "new" ? "new-password" : "current-password"
                  }
                />
              </label>
              <button className="button primary" disabled={!hydrated || saving}>
                {saving ? "Joining…" : "Join organization"}
              </button>
            </fieldset>
          </form>
        </>
      ) : !token && hydrated ? (
        <p className="notice">
          Open the complete invitation link from your email or development
          outbox.
        </p>
      ) : (
        <p>Checking invitation…</p>
      )}
    </AccountFrame>
  );
}
