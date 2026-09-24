"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useDrive } from "@/components/shell";
import { ErrorBox, Loading } from "@/components/ui";

export default function OnboardingPage() {
  const router = useRouter();
  const { user, config } = useDrive();
  const [setup, setSetup] = useState<{
    completed: boolean;
    has_interactions: boolean;
  } | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    api<{ completed: boolean; has_interactions: boolean }>("/onboarding")
      .then(setSetup)
      .catch((e) => setError(e.message));
  }, []);
  async function finish(skip: boolean) {
    setPending(true);
    setError("");
    try {
      await api("/onboarding/complete", {
        method: "POST",
        body: JSON.stringify({ skip }),
      });
      router.push("/");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  const owner = ["OWNER", "ADMIN"].includes(user.role);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">GET STARTED</div>
          <h1>Your first quality review</h1>
          <p>
            A short path from your business standards to an interaction you can
            review.
          </p>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {!setup ? (
        <Loading />
      ) : (
        <div className="onboarding-cards">
          <section className="panel setup-card">
            <span className="eyebrow">01 · ORGANIZATION READY</span>
            <h2>{user.organization_name}</h2>
            <p>
              Your organization has its own data and scorecards. Manage access
              from your account.
            </p>
            <Link href="/account">Account & access →</Link>
          </section>
          <section className="panel setup-card">
            <span className="eyebrow">02 · REVIEW YOUR STANDARD</span>
            <h2>Make the scorecard yours</h2>
            <p>
              A 100-point Dispatch QA starter is ready. Review its categories
              and criteria; duplicate it to publish a standard for your
              business. Published versions preserve historical scores.
            </p>
            <Link className="button secondary" href="/rubrics">
              Review scorecards
            </Link>
          </section>
          <section className="panel setup-card">
            <span className="eyebrow">
              {setup.has_interactions
                ? "03 · RECORDING UPLOADED"
                : "03 · ADD YOUR FIRST RECORDING"}
            </span>
            <h2>Turn an interaction into insight</h2>
            <p>
              Choose one WAV, MP3 or M4A recording, up to {config.max_upload_mb}{" "}
              MB. Then review the transcript, evidence and SignalScore.
            </p>
            <Link className="button primary" href="/upload">
              Upload a recording
            </Link>
          </section>
          <div className="setup-finish">
            {owner && (
              <>
                <button
                  className="button primary"
                  disabled={pending || !setup.has_interactions}
                  onClick={() => finish(false)}
                >
                  Finish setup
                </button>
                <button
                  className="button secondary"
                  disabled={pending}
                  onClick={() => finish(true)}
                >
                  Finish setup later
                </button>
              </>
            )}
            <Link href="/">Go to overview</Link>
            <p className="muted">
              You can return to this guide from the workspace navigation.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
