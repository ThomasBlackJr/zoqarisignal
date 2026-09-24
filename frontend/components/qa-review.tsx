"use client";
import { useState } from "react";
import { api, Detail, date, Rubric } from "@/lib/api";
import { ScorecardPicker } from "./scorecard-picker";
import { Dialog } from "./dialog";
import { ErrorBox } from "./ui";
import { CheckCircle2, Lightbulb } from "lucide-react";

type QA = NonNullable<Detail["evaluation"]>;
export function QAReview({
  qa,
  callId,
  onSaved,
  processing,
}: {
  qa: QA | null;
  callId: string;
  onSaved: () => Promise<void>;
  processing: boolean;
}) {
  const [edit, setEdit] = useState<QA["categories"][number] | null>(null);
  const [score, setScore] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<QA[] | null>(null);
  const [correctedMode, setCorrectedMode] = useState(false);
  const [choices, setChoices] = useState<Rubric[]>([]);
  const [active, setActive] = useState<Rubric | null>(null);
  const [message, setMessage] = useState("");
  async function change(reset = false) {
    if (!qa || !edit) return;
    setSaving(true);
    setError("");
    try {
      await api(
        `/calls/${callId}/evaluations/${qa.id}/categories/${edit.key}`,
        {
          method: "POST",
          body: JSON.stringify({
            score: reset ? null : Number(score),
            reason,
            revision: qa.revision,
          }),
        },
      );
      await onSaved();
      setEdit(null);
      setMessage(
        reset
          ? "Original AI score restored. Audit history retained."
          : "Adjustment saved. Final score recalculated.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function review() {
    if (!qa) return;
    setSaving(true);
    setError("");
    try {
      await api(`/calls/${callId}/evaluations/${qa.id}/review`, {
        method: "POST",
        body: JSON.stringify({ revision: qa.revision + 1 }),
      });
      await onSaved();
      setMessage("Review completed.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function requestNew(corrected = false) {
    setError("");
    try {
      const rubrics = await api<Rubric[]>("/rubrics");
      setCorrectedMode(corrected);
      setChoices(rubrics);
      const selected =
        rubrics.find((r) =>
          corrected ? r.id === qa?.rubric_id : r.status === "ACTIVE",
        ) ?? null;
      setActive(selected);
      if (!selected)
        setError(
          "No eligible scorecard is available. An Owner/Admin must publish a scorecard before a new evaluation.",
        );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function reevaluate() {
    if (!qa || !active) return;
    setSaving(true);
    setError("");
    try {
      await api(`/calls/${callId}/reevaluate`, {
        method: "POST",
        body: JSON.stringify({
          rubric_id: active.id,
          use_previous_scorecard: correctedMode,
          evaluation_id: qa.id,
          transcript_revision: qa.current_transcript_revision,
        }),
      });
      setActive(null);
      await onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  const title = (key: string) =>
    qa?.rubric?.find((c) => c.key === key)?.label ?? key.replaceAll("_", " ");
  return (
    <section className="panel qa-panel">
      <div className="panel-heading">
        <div>
          <h2>Quality evaluation</h2>
          <p>
            {qa
              ? `${qa.rubric_name} · Version ${qa.rubric_version}`
              : "Available after transcription"}
          </p>
        </div>
        {qa && (
          <span className={`review-badge ${qa.reviewed_at ? "reviewed" : ""}`}>
            {qa.reviewed_at ? "Reviewed" : "Needs review"}
          </span>
        )}
      </div>
      {qa?.stale && (
        <div className="notice" role="status">
          <strong>Speaker corrections need evaluation</strong>
          <p>
            This score used an earlier transcript revision and is excluded from
            current performance. Re-evaluate the saved transcript with the same
            published scorecard.
          </p>
          <button
            className="button primary"
            disabled={saving || processing}
            onClick={() => requestNew(true)}
          >
            Evaluate corrected transcript
          </button>
        </div>
      )}
      {error && <ErrorBox message={error} />}{" "}
      {message && (
        <p className="success-message" role="status">
          {message}
        </p>
      )}
      {qa ? (
        <>
          <div className="score-summary">
            <div className="final-score">
              <span>{qa.stale ? "OUTDATED SCORE" : "SIGNAL SCORE"}</span>
              <strong>
                {qa.final_score ?? qa.overall_score}
                <small> / 100</small>
              </strong>
              <p>
                {qa.has_overrides
                  ? "Supervisor adjusted"
                  : "Original AI assessment"}
              </p>
            </div>
            <div className="ai-score">
              <span>AI SCORE</span>
              <strong>
                {qa.overall_score}
                <small> / 100</small>
              </strong>
              <p>Original score preserved</p>
            </div>
          </div>
          <p className="qa-summary">{qa.summary}</p>
          <div className="category-list">
            {qa.categories.map((c) => (
              <details key={c.key} open>
                <summary>
                  <span>
                    {title(c.key)}
                    {c.overridden && (
                      <small className="manual-label">Manually adjusted</small>
                    )}
                  </span>
                  <strong>
                    {c.final_score ?? c.score}
                    <small> / {c.max_score}</small>
                  </strong>
                </summary>
                <div className="category-bar">
                  <span
                    style={{
                      width: `${((c.final_score ?? c.score) / c.max_score) * 100}%`,
                    }}
                  />
                </div>
                <p>{c.explanation}</p>
                {c.evidence.map((q, i) => (
                  <blockquote key={i}>{q}</blockquote>
                ))}
                <div className="category-actions">
                  <span>
                    AI: {c.score} / {c.max_score}
                  </span>
                  <button
                    className="text-link"
                    disabled={processing}
                    onClick={() => {
                      setEdit(c);
                      setScore(String(c.final_score ?? c.score));
                      setReason("");
                      setError("");
                    }}
                  >
                    Adjust {title(c.key)}
                  </button>
                </div>
              </details>
            ))}
          </div>
          <div className="coaching">
            <h3>
              <CheckCircle2 size={17} />
              Strengths
            </h3>
            <ul>
              {qa.strengths.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
            <h3>
              <Lightbulb size={17} />
              Coaching opportunities
            </h3>
            <ul>
              {qa.coaching_opportunities.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
          <div className="review-controls">
            <h3>Supervisor review</h3>
            <p>
              Verify the evidence and scores against the recording before
              completing this review.
            </p>
            <div className="form-actions">
              <button
                className="button primary"
                disabled={saving || processing || !!qa.reviewed_at}
                onClick={review}
              >
                {qa.reviewed_at ? "Review completed" : "Complete review"}
              </button>
              <button
                className="button secondary"
                disabled={saving || processing}
                onClick={() => requestNew()}
              >
                New QA evaluation
              </button>
            </div>
          </div>
          {!!qa.adjustments?.length && (
            <details className="audit-history">
              <summary>
                Score adjustment history ({qa.adjustments.length})
              </summary>
              {[...qa.adjustments].reverse().map((a) => (
                <article key={a.id}>
                  <strong>
                    {title(a.category_key)} · {a.previous_score} →{" "}
                    {a.score ?? "AI score (reset)"}
                  </strong>
                  <p>{a.reason}</p>
                  <small>
                    {a.actor_name} · {date(a.changed_at)}
                  </small>
                </article>
              ))}
            </details>
          )}
          <details className="audit-history">
            <summary>Evaluation scorecard</summary>
            {qa.rubric?.map((c) => (
              <p key={c.key}>
                <strong>
                  {c.label} · {c.max_score} points
                </strong>
                <br />
                {c.criteria}
              </p>
            ))}
          </details>
          <div className="panel-foot">
            <span>
              {qa.provider} · {qa.model} · AI-assisted review
            </span>
            <button
              className="text-link"
              onClick={async () => {
                try {
                  setHistory(await api<QA[]>(`/calls/${callId}/evaluations`));
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Evaluation history
            </button>
          </div>
        </>
      ) : (
        <div className="empty">
          <CheckCircle2 size={30} />
          <h3>Evaluation pending</h3>
          <p>The QA review follows successful transcription.</p>
        </div>
      )}
      {edit && (
        <Dialog
          title={`Adjust ${title(edit.key)}`}
          onClose={() => !saving && setEdit(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void change();
            }}
          >
            <p>
              Original AI score:{" "}
              <strong>
                {edit.score} / {edit.max_score}
              </strong>
            </p>
            <label>
              Supervisor score
              <input
                autoFocus
                type="number"
                min={0}
                max={edit.max_score}
                step={1}
                required
                value={score}
                onChange={(e) => setScore(e.target.value)}
              />
            </label>
            <label>
              Reason for adjustment
              <textarea
                required
                maxLength={2000}
                rows={4}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            {error && <ErrorBox message={error} />}
            <div className="form-actions">
              {edit.overridden && (
                <button
                  type="button"
                  className="button secondary"
                  disabled={saving || !reason.trim()}
                  onClick={() => change(true)}
                >
                  Reset to AI score
                </button>
              )}
              <button
                className="button primary"
                disabled={saving || !reason.trim()}
              >
                {saving ? "Saving…" : "Save adjustment"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
      {active && (
        <Dialog
          title="Request a new QA evaluation"
          onClose={() => !saving && setActive(null)}
        >
          {!correctedMode && (
            <ScorecardPicker
              value={active.id}
              onChange={(id) =>
                setActive(choices.find((r) => r.id === id) ?? active)
              }
              disabled={saving}
            />
          )}
          {correctedMode && (
            <p>
              Corrected transcript: the previous scorecard version is pinned,
              including if it is now archived.
            </p>
          )}
          <p>
            Evaluate this saved transcript using{" "}
            <strong>
              {active.name} · {active.version}
            </strong>
            ?
          </p>
          <p>
            The existing evaluation and adjustments remain in history. This
            sends one QA request to the configured provider and may incur QA
            usage charges. No transcription request is made.
          </p>
          {error && <ErrorBox message={error} />}
          <div className="form-actions">
            <button
              className="button secondary"
              disabled={saving}
              onClick={() => setActive(null)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={saving}
              onClick={reevaluate}
            >
              Start new evaluation
            </button>
          </div>
        </Dialog>
      )}
      {history && (
        <Dialog title="Evaluation history" onClose={() => setHistory(null)}>
          {history.map((h) => (
            <details key={h.id} className="history-evaluation">
              <summary>
                {h.rubric_name} · {h.rubric_version} · Final {h.final_score} /
                AI {h.overall_score}
              </summary>
              <p>
                {date(h.created_at)} · {h.provider} · {h.model} · Transcript
                revision {h.transcript_revision ?? 0}
              </p>
              <p>{h.summary}</p>
              {h.categories.map((c) => (
                <div key={c.key}>
                  <strong>
                    {h.rubric?.find((r) => r.key === c.key)?.label ?? c.key}:{" "}
                    {c.final_score} / {c.max_score} (AI {c.score})
                  </strong>
                  <p>{c.explanation}</p>
                  {c.evidence.map((q, i) => (
                    <blockquote key={i}>{q}</blockquote>
                  ))}
                </div>
              ))}
              {h.adjustments.map((a) => (
                <p key={a.id}>
                  {a.actor_name} · {date(a.changed_at)} · {a.reason} ·{" "}
                  {a.previous_score} → {a.score ?? "reset"}
                </p>
              ))}
            </details>
          ))}
        </Dialog>
      )}
    </section>
  );
}
