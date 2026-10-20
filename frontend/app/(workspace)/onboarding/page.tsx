"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Building2, BookOpen, Upload, Headphones, Check } from "lucide-react";
import { api } from "@/lib/api";
import {
  tutorialStepCount,
  useTutorialProgress,
} from "@/lib/tutorial-progress";
import { useDrive } from "@/components/shell";
import { ErrorBox, Loading, UploadLink } from "@/components/ui";
import "@/app/tutorial.css";

type Setup = { completed: boolean; has_interactions: boolean };
export default function OnboardingPage() {
  const router = useRouter();
  const { user, config } = useDrive();
  const progress = useTutorialProgress(user);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [replayStep, setReplayStep] = useState<number | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    let active = true;
    api<Setup>("/onboarding")
      .then((value) => {
        if (active) setSetup(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  const owner = ["OWNER", "ADMIN"].includes(user.role);
  const step = replayStep ?? progress.step;
  const done = progress.done || Boolean(setup?.completed);
  const replaying = replayStep !== null;
  function move(next: number) {
    if (replaying) setReplayStep(next);
    else progress.save({ step: next, status: "active" });
    heading.current?.focus();
  }
  async function finish() {
    if (!setup) return;
    setPending(true);
    setError("");
    try {
      if (!replaying) {
        // Organization completion remains restricted to Owners/Admins.
        if (owner)
          await api("/onboarding/complete", {
            method: "POST",
            body: JSON.stringify({ skip: !setup.has_interactions }),
          });
        progress.save({ step: tutorialStepCount - 1, status: "completed" });
      }
      router.push("/");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  const steps = [
    {
      title: "Know your workspace",
      Icon: Building2,
      description: `Your calls and scorecards stay within ${user.organization_name || "your organization"}. Check your membership and access here.`,
      action: (
        <Link className="button secondary" href="/account">
          Account &amp; access
        </Link>
      ),
    },
    {
      title: "Choose your scorecard",
      Icon: BookOpen,
      description: owner
        ? "Review the starter scorecard. Duplicate it to adapt and publish your own quality standard."
        : "Explore the published scorecards your organization uses to evaluate calls.",
      action: (
        <Link className="button secondary" href="/rubrics">
          Review scorecards
        </Link>
      ),
    },
    {
      title: "Upload your first call",
      Icon: Upload,
      description: `Choose a WAV, MP3 or M4A recording up to ${config.max_upload_mb} MB, then select a scorecard for analysis.`,
      action: (
        <UploadLink
          disabled={!user.operational_access || !user.can_review}
          disabledLabel={
            user.can_review
              ? "Beta access required"
              : "Upload unavailable for your role"
          }
        />
      ),
    },
    {
      title: "Review the evidence",
      Icon: Headphones,
      description:
        "Open a call to review its transcript, score and supporting evidence. Your dashboard brings the next review priorities together.",
      action: (
        <Link className="button secondary" href="/calls">
          Open calls &amp; audits
        </Link>
      ),
    },
  ];
  const current = steps[step];
  return (
    <div className="tutorial-wrap">
      <div className="page-heading">
        <div>
          <div className="eyebrow">GET STARTED</div>
          <h1>Tutorial</h1>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {!progress.ready || (!setup && !done) ? (
        error ? (
          <button
            className="button secondary"
            onClick={() => {
              setError("");
              setAttempt((value) => value + 1);
            }}
          >
            Reload tutorial
          </button>
        ) : (
          <Loading />
        )
      ) : done && !replaying ? (
        <section
          className="panel tutorial-complete"
          aria-label="Tutorial status"
        >
          <Check size={24} aria-hidden="true" />
          <h2>
            {progress.status === "dismissed" &&
            !setup?.completed &&
            !user.onboarding_completed
              ? "Tutorial dismissed"
              : "You’re all set"}
          </h2>
          <p>You can revisit these steps whenever you need them.</p>
          <div className="tutorial-actions">
            <Link className="button primary" href="/">
              Open dashboard
            </Link>
            <button
              className="button secondary"
              disabled={!setup}
              onClick={() => setReplayStep(0)}
            >
              Review tutorial
            </button>
          </div>
        </section>
      ) : (
        <section
          className="panel tutorial-card"
          aria-label="Signal tutorial"
          aria-busy={pending}
        >
          <div className="tutorial-progress">
            <span role="status">
              Step {step + 1} of {tutorialStepCount}
            </span>
            <progress
              value={step + 1}
              max={tutorialStepCount}
              aria-label="Tutorial progress"
            />
          </div>
          <div className="tutorial-body" aria-live="polite">
            <span className="tutorial-icon">
              <current.Icon size={24} aria-hidden="true" />
            </span>
            <h2 ref={heading} tabIndex={-1}>
              {current.title}
            </h2>
            <p>{current.description}</p>
            {step === 2 && setup?.has_interactions && (
              <p className="tutorial-hint">
                <Check size={14} aria-hidden="true" /> Your workspace already
                has a recording.
              </p>
            )}
            {current.action}
          </div>
          <div className="tutorial-controls">
            <button
              className="button secondary"
              disabled={step === 0 || pending}
              onClick={() => move(step - 1)}
            >
              Back
            </button>
            <button
              className="button primary"
              disabled={pending}
              onClick={() =>
                step < tutorialStepCount - 1 ? move(step + 1) : void finish()
              }
            >
              {pending
                ? "Finishing…"
                : step === tutorialStepCount - 1
                  ? "Finish tutorial"
                  : "Next"}
            </button>
          </div>
          <div className="tutorial-dismiss">
            <button
              className="text-link"
              disabled={pending}
              onClick={() => {
                if (!replaying) progress.save({ step, status: "dismissed" });
                router.push("/");
              }}
            >
              {replaying ? "Close tutorial" : "Not interested"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
