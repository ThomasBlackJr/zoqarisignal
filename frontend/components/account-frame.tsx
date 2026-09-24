import { Appearance } from "./preferences";
import Link from "next/link";
import { Brand } from "./ui";

export function AccountFrame({
  children,
  invitation = false,
}: {
  children: React.ReactNode;
  invitation?: boolean;
}) {
  return (
    <main className="account-page">
      <header className="account-header">
        <Link href="/login" aria-label="Signal sign in">
          <Brand />
        </Link>
        <Appearance />
      </header>
      <div className="account-grid">
        <section className="account-intro">
          <div className="eyebrow">ZOQARI SIGNAL</div>
          <h1>
            Build a clearer picture.
            <br />
            <em>One interaction at a time.</em>
          </h1>
          <p>
            Your business. Your scorecards. A shared view of service quality.
          </p>
          <div className="account-steps">
            <span>
              {invitation
                ? "01 · Accept your invitation"
                : "01 · Create your account"}
            </span>
            <span>
              {invitation
                ? "02 · Join the existing business"
                : "02 · Set up your business"}
            </span>
            <span>
              {invitation
                ? "03 · Work with your team"
                : "03 · Review your first interaction"}
            </span>
          </div>
        </section>
        <section className="account-card">{children}</section>
      </div>
    </main>
  );
}
