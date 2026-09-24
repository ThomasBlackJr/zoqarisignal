"use client";
import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useHydrated } from "@/lib/use-hydrated";
import { AccountFrame } from "./account-frame";
import { ErrorBox } from "./ui";

type Kind = "register" | "forgot-password" | "verify-email" | "reset-password";
const titles = {
  register: "Create your Signal account",
  "forgot-password": "Reset your password",
  "verify-email": "Verify your email",
  "reset-password": "Choose a new password",
};

function subscribeHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}
const readHash = () => window.location.hash;
const serverHash = () => "";

export function AccountForm({ kind }: { kind: Kind }) {
  const router = useRouter();
  const hydrated = useHydrated();
  const hash = useSyncExternalStore(subscribeHash, readHash, serverHash);
  const token = new URLSearchParams(hash.slice(1)).get("token") || "";
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    const data = new FormData(event.currentTarget);
    const body =
      kind === "register"
        ? {
            name: data.get("name"),
            email: data.get("email"),
            password: data.get("password"),
          }
        : kind === "forgot-password"
          ? { email: data.get("email") }
          : kind === "verify-email"
            ? { token }
            : { token, password: data.get("password") };
    try {
      const result = await api<{
        message?: string;
        mail_delivery?: string;
        challenge?: string;
      }>("/auth/" + kind, { method: "POST", body: JSON.stringify(body) });
      if (token)
        window.history.replaceState(null, "", window.location.pathname);
      if (kind === "register") {
        router.replace(
          `/verify-email#challenge=${encodeURIComponent(result.challenge || "")}`,
        );
        return;
      }
      setMessage(
        (result.message || "Done.") +
          (result.mail_delivery === "local"
            ? " Local development: no email was sent. The link is in the private backend mail outbox."
            : ""),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <AccountFrame>
      <div className="eyebrow">YOUR ACCOUNT</div>
      <h2>{titles[kind]}</h2>
      <p className="muted">
        {kind === "register"
          ? "Start with your business email. Operational access requires a subscription."
          : kind === "forgot-password"
            ? "Request a link to recover access to your account."
            : "Links expire and can be used once. Confirm below to continue."}
      </p>
      {error && <ErrorBox message={error} />}
      {message ? (
        <div role="status">
          <p>{message}</p>
          <Link
            className="button primary"
            href={kind === "verify-email" ? "/account" : "/login"}
          >
            {kind === "verify-email"
              ? "Continue to account"
              : "Back to sign in"}
          </Link>
        </div>
      ) : (
        <form className="account-form" method="post" onSubmit={submit}>
          {kind === "register" && (
            <>
              <label htmlFor="name">Your name</label>
              <input
                id="name"
                name="name"
                autoComplete="name"
                maxLength={100}
                required
              />
            </>
          )}
          {(kind === "register" || kind === "forgot-password") && (
            <>
              <label htmlFor="email">Business email</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                maxLength={254}
                required
              />
            </>
          )}
          {(kind === "register" || kind === "reset-password") && (
            <>
              <label htmlFor="password">New password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                aria-describedby="password-help"
                required
              />
              <small id="password-help">
                Use at least 12 characters. A unique passphrase works well.
              </small>
            </>
          )}
          {(kind === "verify-email" || kind === "reset-password") && !token && (
            <p role="status">
              Open the full link from your email. If it has expired, request a
              new link.
            </p>
          )}
          <button
            className="button primary"
            disabled={
              !hydrated ||
              pending ||
              ((kind === "verify-email" || kind === "reset-password") && !token)
            }
          >
            {pending
              ? "Working…"
              : kind === "register"
                ? "Create account"
                : kind === "forgot-password"
                  ? "Request reset link"
                  : kind === "verify-email"
                    ? "Confirm email verification"
                    : "Change password"}
          </button>
        </form>
      )}
      <div className="account-links">
        <Link href="/login">Sign in</Link>
        {kind === "reset-password" && (
          <Link href="/forgot-password">Request a new link</Link>
        )}
        {kind === "verify-email" && (
          <Link href="/account">Resend verification</Link>
        )}
      </div>
    </AccountFrame>
  );
}
