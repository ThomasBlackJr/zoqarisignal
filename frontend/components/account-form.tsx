"use client";
import { useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, Account, accountDestination } from "@/lib/api";
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
  const submitting = useRef(false);
  const [nextStep, setNextStep] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    setError("");
    const data = new FormData(event.currentTarget);
    if (kind === "register" || kind === "reset-password") {
      const password = String(data.get("password") || "");
      const length = Array.from(password).length;
      if (length < 12 || length > 256) {
        setError(
          "Use at least 12 characters and no more than 256 characters for your password.",
        );
        return;
      }
    }
    if (!event.currentTarget.reportValidity()) return;
    submitting.current = true;
    setPending(true);
    let navigating = false;
    function navigate(destination: string) {
      navigating = true;
      setNextStep(destination);
      router.replace(destination);
    }
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
        signed_in?: boolean;
      }>("/auth/" + kind, { method: "POST", body: JSON.stringify(body) });
      if (token)
        window.history.replaceState(null, "", window.location.pathname);
      if (kind === "register") {
        if (result.signed_in) {
          const account = await api<Account>("/account");
          if (!account.email_verified) {
            let notice = "";
            try {
              await api("/auth/verification", { method: "POST" });
            } catch (e) {
              notice = (e as Error).message;
            }
            navigate(
              `/verify-email#email=${encodeURIComponent(account.email.replace(/^(.).*(@.*)$/, "$1***$2"))}${notice ? `&notice=${encodeURIComponent(notice)}` : ""}`,
            );
          } else navigate(accountDestination(account));
          return;
        }
        navigate(
          `/verify-email#challenge=${encodeURIComponent(result.challenge || "")}&email=${encodeURIComponent(String(data.get("email")).replace(/^(.).*(@.*)$/, "$1***$2"))}`,
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
      if (!navigating) {
        submitting.current = false;
        setPending(false);
      }
    }
  }
  return (
    <AccountFrame>
      <div className="eyebrow">YOUR ACCOUNT</div>
      <h2>{titles[kind]}</h2>
      <p className="muted">
        {kind === "register"
          ? "Create an account with your business email. Join your team or request free pilot access for your organization. Already registered? Sign in instead."
          : kind === "forgot-password"
            ? "Request a link to recover access to your account."
            : "Links expire and can be used once. Confirm below to continue."}
      </p>
      {error && <ErrorBox message={error} />}
      {nextStep ? (
        <div role="status">
          <p>Registration submitted. Opening your next step…</p>
          <Link className="button primary" href={nextStep}>
            Continue
          </Link>
        </div>
      ) : message ? (
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
          <fieldset disabled={pending}>
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
            {(kind === "verify-email" || kind === "reset-password") &&
              !token && (
                <p role="status">
                  Open the full link from your email. If it has expired, request
                  a new link.
                </p>
              )}
            <button
              className="button primary"
              disabled={
                !hydrated ||
                pending ||
                ((kind === "verify-email" || kind === "reset-password") &&
                  !token)
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
          </fieldset>
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
