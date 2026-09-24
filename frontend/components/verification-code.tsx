"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useHydrated } from "@/lib/use-hydrated";
import { AccountFrame } from "./account-frame";
import { AccountForm } from "./account-form";
import { ErrorBox } from "./ui";
const subscribe = (fn: () => void) => {
  window.addEventListener("hashchange", fn);
  return () => window.removeEventListener("hashchange", fn);
};
export function VerificationCode() {
  const hash = useSyncExternalStore(
    subscribe,
    () => window.location.hash,
    () => "",
  );
  const params = new URLSearchParams(hash.slice(1));
  const challenge = params.get("challenge");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(60);
  const [mode, setMode] = useState("");
  const [done, setDone] = useState(false);
  const hydrated = useHydrated();
  useEffect(() => {
    api<{ mail_delivery: string }>("/auth/options")
      .then((v) => setMode(v.mail_delivery))
      .catch(() => {});
    const timer = setInterval(
      () => setCooldown((n) => Math.max(0, n - 1)),
      1000,
    );
    return () => clearInterval(timer);
  }, []);
  if (params.has("token")) return <AccountForm kind="verify-email" />;
  return (
    <AccountFrame>
      <div className="eyebrow">VERIFY YOUR ACCOUNT</div>
      <h2>Verify your business email</h2>
      <p>
        Enter the six-digit code from your email. It expires after 15 minutes
        and can be used once.
      </p>
      {mode === "local" && (
        <p className="development-note">
          LOCAL DEVELOPMENT · No email was sent. The code is in the private
          backend mail outbox.
        </p>
      )}
      {error && <ErrorBox message={error} />}{" "}
      {message && <p role="status">{message}</p>}
      {done ? (
        <Link className="button primary" href="/account">
          Continue to account
        </Link>
      ) : (
        <>
          <form
            method="post"
            className="account-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                await api("/auth/verify-email", {
                  method: "POST",
                  body: JSON.stringify({
                    code,
                    ...(challenge ? { challenge } : {}),
                  }),
                });
                window.history.replaceState(null, "", "/verify-email");
                setDone(true);
                setMessage("Email verified.");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label htmlFor="verification-code">Verification code</label>
            <input
              id="verification-code"
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              minLength={6}
              maxLength={6}
              required
              value={code}
              onChange={(e) =>
                setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
              }
              style={{
                fontSize: 28,
                letterSpacing: ".4em",
                textAlign: "center",
              }}
            />
            <button
              className="button primary"
              disabled={!hydrated || busy || code.length !== 6}
            >
              {busy ? "Verifying…" : "Verify email"}
            </button>
          </form>
          <button
            className="button secondary"
            disabled={!hydrated || busy || cooldown > 0}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                const v = await api<{ challenge?: string }>(
                  challenge
                    ? "/auth/verification-code/resend"
                    : "/auth/verification",
                  {
                    method: "POST",
                    ...(challenge
                      ? { body: JSON.stringify({ challenge }) }
                      : {}),
                  },
                );
                if (v.challenge) {
                  window.history.replaceState(
                    null,
                    "",
                    `#challenge=${encodeURIComponent(v.challenge)}`,
                  );
                  window.dispatchEvent(new HashChangeEvent("hashchange"));
                }
                setCooldown(60);
                setCode("");
                setMessage(
                  "A new code was requested. Use the most recent message.",
                );
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {cooldown ? `Resend code in ${cooldown}s` : "Resend code"}
          </button>
          <p className="muted">
            Already have an account? <Link href="/login">Sign in</Link> or{" "}
            <Link href="/forgot-password">reset your password</Link>.
          </p>
        </>
      )}
    </AccountFrame>
  );
}
