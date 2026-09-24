"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, AudioLines, ShieldCheck, Route } from "lucide-react";
import { api, Account, accountDestination } from "@/lib/api";
import { Brand, ErrorBox } from "@/components/ui";
import { useHydrated } from "@/lib/use-hydrated";

export default function LoginPage() {
  const router = useRouter();
  const hydrated = useHydrated();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    const data = new FormData(event.currentTarget);
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: data.get("email"),
          password: data.get("password"),
        }),
      });
      router.replace(accountDestination(await api<Account>("/account")));
    } catch (e) {
      setError((e as Error).message);
      setPending(false);
    }
  }
  return (
    <main className="login">
      <section className="login-story">
        <Brand />
        <div className="login-message">
          <div className="eyebrow">
            <span /> EVERY CONVERSATION COUNTS
          </div>
          <h1>
            Clarity for every call.
            <br />
            <em>Confidence in every interaction.</em>
          </h1>
          <p>
            One place to review customer conversations, understand service
            quality, and help your team move forward.
          </p>
          <div className="signal-graphic" aria-hidden="true">
            {[
              18, 30, 21, 47, 62, 33, 73, 92, 55, 35, 66, 100, 79, 41, 24, 65,
              83, 53, 31, 48, 74, 42, 21, 33, 17, 44, 58, 29, 15,
            ].map((h, i) => (
              <i key={i} style={{ height: `${h}%` }} />
            ))}
          </div>
          <div className="login-features">
            <span>
              <AudioLines size={18} />
              Call intelligence
            </span>
            <span>
              <ShieldCheck size={18} />
              Quality verification
            </span>
            <span>
              <Route size={18} />
              Better operations
            </span>
          </div>
        </div>
        <p className="login-caption">
          Quality intelligence for every interaction.
        </p>
      </section>
      <section className="login-form-wrap">
        <form onSubmit={submit} method="post" className="login-form">
          <div className="eyebrow">YOUR OPERATIONS, IN FOCUS</div>
          <h2>Welcome to Signal</h2>
          <p className="muted">Sign in to your organization’s workspace.</p>
          {error && <ErrorBox message={error} />}
          <label htmlFor="email">Work email</label>
          <input
            id="email"
            name="email"
            type="email"
            placeholder="you@company.com"
            required
            autoComplete="username"
            maxLength={254}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            placeholder="Enter your password"
            required
            autoComplete="current-password"
            maxLength={256}
          />
          <button className="button primary login-submit" disabled={!hydrated || pending}>
            {pending ? "Signing in…" : "Sign in to Signal"}
            <ArrowRight size={18} />
          </button>
          <div className="account-links">
            <Link href="/register">Create an account</Link>
            <Link href="/forgot-password">Forgot password?</Link>
          </div>
        </form>
        <small className="login-legal">
          A Zoqari product. Built for better interactions.
        </small>
      </section>
    </main>
  );
}
