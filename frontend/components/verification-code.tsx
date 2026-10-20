"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useHydrated } from "@/lib/use-hydrated";
import { AccountFrame } from "./account-frame";
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
  const resendAt = useRef(0);
  const [mode, setMode] = useState("");
  const [done, setDone] = useState(false);
  const hydrated = useHydrated();
  useEffect(() => {
    api<{ mail_delivery: string }>("/auth/options")
      .then((v) => setMode(v.mail_delivery))
      .catch(() => {});
    resendAt.current = Date.now() + 60000;
    const timer = setInterval(
      () => setCooldown(Math.max(0, Math.ceil((resendAt.current - Date.now()) / 1000))),
      1000,
    );
    return () => clearInterval(timer);
  }, []);
  return (
    <AccountFrame>
      <div className="eyebrow">VERIFY YOUR ACCOUNT</div>
      <h2>Verify your email</h2>
      <p>
        If this address needs verification, a 6-digit code has been requested
        {params.get("email")
          ? ` for ${params.get("email")}`
          : " for your email address"}
        . It expires after 15 minutes and can be used once. Already verified?
        Sign in instead.
      </p>
      {params.has("token") && (
        <p className="muted">
          Verification links are no longer used. Sign in to request a new
          six-digit code.
        </p>
      )}
      {mode === "local" && (
        <p className="development-note">
          LOCAL DEVELOPMENT · No email was sent. The code is in the private
          backend mail outbox.
        </p>
      )}
      {error && <ErrorBox message={error} />}{" "}
      {params.get("notice") && (
        <p role="status">
          {params.get("notice")}. Check your latest email, or request a new code
          below.
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {done ? (
        <Link className="button primary" href="/">
          Continue to Signal
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
                    `#challenge=${encodeURIComponent(v.challenge)}${params.get("email") ? `&email=${encodeURIComponent(params.get("email")!)}` : ""}`,
                  );
                  window.dispatchEvent(new HashChangeEvent("hashchange"));
                }
                resendAt.current = Date.now() + 60000;
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
          <p>
            <Link href="/register">Change email</Link> · This starts signup with
            a different address; it does not change an existing account.
          </p>
        </>
      )}
    </AccountFrame>
  );
}
