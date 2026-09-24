"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Dialog } from "./dialog";
import { ErrorBox, Loading } from "./ui";

export type Issue = {
  recommendation?: string | null;
  recommendation_synthetic?: boolean;
  id: string;
  name: string;
  rubric_name: string;
  rubric_version: string;
  criteria: string;
  description: string;
  max_score: number;
  eligible: number;
  occurrences: number;
  affected_employees: number;
  unassigned: number;
  percent: number;
  limited_sample: boolean;
  coaching_ready: boolean;
};
export type Interaction = {
  id: string;
  filename: string;
  employee_id: string | null;
  employee_name: string | null;
  manager_id: string | null;
  manager_name: string | null;
  score: number | null;
  status: string;
  stale: boolean;
  needs_review: boolean;
  rubric_name: string | null;
  rubric_version: string | null;
  is_demo: boolean;
};
export type Briefing = {
  signal_score: number | null;
  analyzed: number;
  limited_sample: boolean;
  total: number;
  active_employees: number;
  needs_attention: number;
  requiring_review: number;
  stale: number;
  failed: number;
  awaiting: number;
  period: string;
  issues: Issue[];
  recent: Interaction[];
  teams: {
    id: string;
    name: string;
    active: boolean;
    direct_reports: number;
    interactions: number;
    analyzed: number;
    limited_sample: boolean;
    score: number | null;
  }[];
};
type Draft = {
  observation: string;
  recommendation: string;
  subject: string;
  body: string;
  provider: string;
  created_at: number;
  synthetic: boolean;
  fingerprint: string;
};
type Details = Issue & {
  fingerprint: string;
  draft: Draft | null;
  evidence: (Interaction & {
    evaluation_id: string;
    category_score: number;
    original_score: number;
    overridden: boolean;
    explanation: string;
    quotes: string[];
  })[];
};

export function Observation({ issue }: { issue: Issue }) {
  return (
    <p>
      {issue.occurrences} of {issue.eligible} evaluated interactions (
      {issue.percent}%) below maximum · {issue.affected_employees} employees
      affected{issue.unassigned > 0 && ` · ${issue.unassigned} unassigned`}
    </p>
  );
}

export function IssueDialog({
  id,
  email,
  onClose,
}: {
  id: string;
  email: boolean;
  onClose: () => void;
}) {
  const [data, setData] = useState<Details | null>(null);
  const [offset, setOffset] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showEmail, setShowEmail] = useState(email);
  const [copied, setCopied] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const initialized = useRef(false);
  useEffect(() => {
    let alive = true;
    api<Details>(`/briefing/issues/${id}?offset=${offset}`)
      .then((v) => {
        if (!alive) return;
        setData(v);
        if (!initialized.current) {
          initialized.current = true;
          setDraft(v.draft);
          setSubject(v.draft?.subject ?? "");
          setBody(v.draft?.body ?? "");
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [id, offset]);
  async function generate(regenerate = false) {
    if (!data) return;
    setBusy(true);
    setError("");
    setCopied(false);
    setConfirmReplace(false);
    try {
      const v = await api<Draft>(`/briefing/issues/${id}/generate`, {
        method: "POST",
        body: JSON.stringify({ fingerprint: data.fingerprint, regenerate }),
      });
      setDraft(v);
      setSubject(v.subject);
      setBody(v.body);
      setDirty(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={showEmail ? "Create team communication" : "Quality issue evidence"}
      onClose={onClose}
    >
      {error && <ErrorBox message={error} />}
      {!data ? (
        <Loading />
      ) : (
        <>
          <h3>{data.name}</h3>
          <p className="muted">
            {data.rubric_name} · v{data.rubric_version} · All time ·
            Organization
          </p>
          <div className="briefing-observation">
            <strong>Data observation</strong>
            <Observation issue={data} />
            <small>
              Below maximum category points, not individual policy failures.
              Current audited scores only.
            </small>
          </div>
          <details>
            <summary>Exact scorecard requirements</summary>
            <p>{data.description}</p>
            <p className="preserve-lines">{data.criteria}</p>
          </details>
          {data.coaching_ready ? (
            <section className="coaching-result">
              <h3>
                {draft?.synthetic
                  ? "Synthetic recommendation"
                  : "AI-assisted recommendation"}
              </h3>
              {draft ? (
                <>
                  <p>{draft.recommendation}</p>
                  <p className="muted">
                    {draft.synthetic
                      ? "Demo provider · synthetic"
                      : "AI-selected action · Signal-grounded wording"}{" "}
                    · Saved {new Date(draft.created_at * 1000).toLocaleString()}
                  </p>
                </>
              ) : (
                <p>
                  Generate a suggested review action and a communication draft
                  using this aggregate and its exact scorecard requirements.
                  Live providers may incur usage.
                </p>
              )}
              {!draft && (
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={() => void generate()}
                >
                  {busy
                    ? "Preparing…"
                    : showEmail
                      ? "Generate email draft"
                      : "Generate coaching recommendation"}
                </button>
              )}
              {draft && !showEmail && (
                <button
                  className="button secondary"
                  onClick={() => setShowEmail(true)}
                >
                  Create Team Email
                </button>
              )}
            </section>
          ) : (
            <p className="notice">
              Not enough evaluated interactions yet to identify reliable
              coaching opportunities. At least five eligible interactions and
              two below-maximum occurrences are required.
            </p>
          )}
          {showEmail && draft && (
            <div className="communication-form">
              <p className="notice">
                Draft only. Review the evidence and wording before copying.
                Signal does not send email. Edits stay in this window until you
                close it.
              </p>
              <label>
                Subject
                <input
                  value={subject}
                  onChange={(e) => {
                    setSubject(e.target.value);
                    setDirty(true);
                    setCopied(false);
                  }}
                />
              </label>
              <label>
                Email draft
                <textarea
                  aria-label="Email draft"
                  rows={14}
                  value={body}
                  onChange={(e) => {
                    setBody(e.target.value);
                    setDirty(true);
                    setCopied(false);
                  }}
                />
              </label>
              <div className="form-actions">
                <button
                  className="button primary"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(
                        `Subject: ${subject}\n\n${body}`,
                      );
                      setCopied(true);
                    } catch {
                      setError(
                        "Copy unavailable. Select and copy the draft text manually.",
                      );
                    }
                  }}
                >
                  Copy draft
                </button>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() =>
                    dirty ? setConfirmReplace(true) : void generate(true)
                  }
                >
                  {busy ? "Preparing…" : "Regenerate"}
                </button>
              </div>
              {confirmReplace && (
                <p>
                  Regenerating replaces your edits and may incur AI usage.{" "}
                  <button
                    className="button secondary"
                    onClick={() => void generate(true)}
                  >
                    Replace edits
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => setConfirmReplace(false)}
                  >
                    Keep edits
                  </button>
                </p>
              )}
              {copied && <p role="status">Draft copied. No email was sent.</p>}
            </div>
          )}
          <h3>Supporting interactions</h3>
          <p className="muted">
            Original QA evidence remains visible alongside the current audited
            category score. Review overrides and full context in the
            interaction.
          </p>
          <div className="issue-evidence">
            {data.evidence.map((e) => (
              <article key={e.id}>
                <div className="briefing-row">
                  <Link className="text-link" href={`/calls/${e.id}`}>
                    {e.filename}
                  </Link>
                  <strong>
                    {e.category_score}/{data.max_score}
                  </strong>
                </div>
                <p>
                  {e.employee_id ? (
                    <Link href={`/employees/${e.employee_id}`}>
                      {e.employee_name}
                    </Link>
                  ) : (
                    "Unassigned"
                  )}
                  {e.manager_id && (
                    <>
                      {" "}
                      ·{" "}
                      <Link href={`/employees/${e.manager_id}/team`}>
                        {e.manager_name}’s team
                      </Link>
                    </>
                  )}
                  {e.is_demo && " · Synthetic demo"}
                </p>
                {e.overridden && (
                  <p>
                    Audited override · Original AI category score{" "}
                    {e.original_score}/{data.max_score}
                  </p>
                )}
                <p>{e.explanation}</p>
                {e.quotes.length ? (
                  e.quotes.map((q, n) => <blockquote key={n}>{q}</blockquote>)
                ) : (
                  <p>No transcript excerpt was supplied for this category.</p>
                )}
              </article>
            ))}
          </div>
          <div className="form-actions">
            <button
              className="button secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous evidence
            </button>
            <span>
              {offset + 1}–{Math.min(offset + 25, data.occurrences)} of{" "}
              {data.occurrences}
            </span>
            <button
              className="button secondary"
              disabled={offset + 25 >= data.occurrences}
              onClick={() => setOffset(offset + 25)}
            >
              More evidence
            </button>
          </div>
          <button className="button secondary" onClick={onClose}>
            Close
          </button>
        </>
      )}
    </Dialog>
  );
}
