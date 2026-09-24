"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import {
  DashboardEditor,
  defaultModules,
  usePreferences,
} from "@/components/preferences";
import { Briefing, IssueDialog, Observation } from "@/components/briefing";
import { useDrive } from "@/components/shell";
import { ErrorBox, Loading, UploadLink } from "@/components/ui";
import "@/app/briefing.css";

export default function DashboardPage() {
  const { user } = useDrive();
  const { value: preferences } = usePreferences();
  const modules = preferences?.modules ?? defaultModules;
  const [data, setData] = useState<Briefing | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<{
    id: string;
    email: boolean;
  } | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let alive = true;
    api<Briefing>("/briefing")
      .then((v) => {
        if (alive) {
          setData(v);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [refresh]);
  const opportunities =
    data?.issues.filter((i) => i.coaching_ready).slice(0, 3) ?? [];
  function content(key: string) {
    if (!data) return null;
    switch (key) {
      case "metrics":
        return (
          <section aria-label="Business Overview">
            <div className="metrics">
              {[
                [
                  "Signal Score",
                  data.signal_score ?? "—",
                  "Current interaction-weighted score / 100",
                ],
                [
                  "Interactions analyzed",
                  data.analyzed,
                  "Latest eligible evaluation per interaction",
                ],
                [
                  "Need attention",
                  data.needs_attention,
                  "Review, outdated scores or failed processing",
                ],
                [
                  "Active employees",
                  data.active_employees,
                  "Tracked people in your organization",
                ],
              ].map(([label, value, note]) => (
                <article className="metric" key={label}>
                  <div className="metric-top">{label}</div>
                  <div className="metric-value">{value}</div>
                  <p>{note}</p>
                </article>
              ))}
            </div>
            <p className="briefing-footnote">
              {data.period}. Scores may span different scorecards.{" "}
              {data.limited_sample &&
                "Limited sample: fewer than five current evaluations."}
            </p>
          </section>
        );
      case "attention":
        return (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Needs Attention</h2>
                <p>
                  {data.needs_attention
                    ? "Start with the interactions that need a decision."
                    : "No outstanding review or processing issues."}
                </p>
              </div>
              <strong>{data.needs_attention}</strong>
            </div>
            <div className="briefing-attention">
              <Link href="/calls?needs_review=true">
                <strong>{data.requiring_review}</strong>
                <span>Require review</span>
                <small>Includes {data.stale} outdated evaluations</small>
              </Link>
              <Link href="/calls?status=failed">
                <strong>{data.failed}</strong>
                <span>Processing failures</span>
                <small>Open an interaction to inspect or retry</small>
              </Link>
            </div>
          </section>
        );
      case "issues":
        return (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Frequent Quality Issues</h2>
                <p>
                  Recurring categories below maximum points, grouped by exact
                  scorecard version.
                </p>
              </div>
            </div>
            {data.issues.length ? (
              <div className="briefing-issues">
                {data.issues.map((i) => (
                  <article key={i.id}>
                    <div className="briefing-row">
                      <div>
                        <h3>{i.name}</h3>
                        <small>
                          {i.rubric_name} · v{i.rubric_version}
                        </small>
                      </div>
                      <span className="issue-count">
                        {i.occurrences}
                        <small>occurrences</small>
                      </span>
                    </div>
                    <Observation issue={i} />
                    <div className="briefing-row">
                      <small>
                        {i.limited_sample
                          ? "Limited sample"
                          : "Current audited scores"}{" "}
                        · Not criterion-level failure counts
                      </small>
                      <button
                        className="button secondary"
                        onClick={() => setSelected({ id: i.id, email: false })}
                      >
                        View evidence
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="empty">
                No below-maximum categories in current evaluations.
              </p>
            )}
          </section>
        );
      case "teams":
        return (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Team Performance</h2>
                <p>
                  Current direct reports · each eligible interaction has equal
                  weight
                </p>
              </div>
              <Link className="text-link" href="/employees/managers">
                View managers
              </Link>
            </div>
            {data.teams.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Manager</th>
                      <th>Employees</th>
                      <th>Analyzed</th>
                      <th>Signal Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.teams.map((t) => (
                      <tr key={t.id}>
                        <td>
                          <Link
                            className="text-link"
                            href={`/employees/${t.id}/team`}
                          >
                            {t.name}
                          </Link>
                          {!t.active && <small> · Archived</small>}
                        </td>
                        <td>{t.direct_reports}</td>
                        <td>
                          {t.analyzed} / {t.interactions}
                        </td>
                        <td>
                          {t.score ?? "—"}
                          {t.limited_sample && <small> · Limited sample</small>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty">
                Designate managers and assign direct reports in Employees to see
                team performance.
              </p>
            )}
          </section>
        );
      case "coaching":
        return (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Coaching Opportunities</h2>
                <p>
                  Verified observations first. AI-assisted review actions on
                  request.
                </p>
              </div>
            </div>
            {opportunities.length ? (
              <div className="briefing-issues">
                {opportunities.map((i) => (
                  <article key={i.id}>
                    <h3>{i.name}</h3>
                    <small>
                      {i.rubric_name} · v{i.rubric_version}
                    </small>
                    <Observation issue={i} />
                    {i.recommendation && (
                      <div className="briefing-observation">
                        <strong>
                          {i.recommendation_synthetic
                            ? "Synthetic recommendation"
                            : "AI-assisted recommendation"}
                        </strong>
                        <p>{i.recommendation}</p>
                      </div>
                    )}
                    <div className="form-actions">
                      <button
                        className="button secondary"
                        onClick={() => setSelected({ id: i.id, email: false })}
                      >
                        Review coaching & evidence
                      </button>
                      <button
                        className="button secondary"
                        onClick={() => setSelected({ id: i.id, email: true })}
                      >
                        Create Team Email
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="empty">
                Not enough recurring observations yet. Coaching requires five
                eligible evaluations per scorecard and two below-maximum
                occurrences.
              </p>
            )}
          </section>
        );
      case "recommendations":
        return (
          <section className="panel signal-recommends">
            <div className="panel-heading">
              <div>
                <h2>Signal Recommends</h2>
                <p>
                  Up to three review priorities, ordered by observed occurrence
                  count.
                </p>
              </div>
            </div>
            {opportunities.length ? (
              opportunities.map((i) => (
                <div className="recommendation-row" key={i.id}>
                  <div>
                    <h3>Review {i.name}</h3>
                    <p>
                      {i.occurrences} below-maximum scores · {i.rubric_name} v
                      {i.rubric_version}
                    </p>
                    <small>
                      Review the evidence before choosing a team reminder.
                    </small>
                  </div>
                  <div className="form-actions">
                    <button
                      className="button secondary"
                      onClick={() => setSelected({ id: i.id, email: false })}
                    >
                      View evidence
                    </button>
                    <button
                      className="button primary"
                      onClick={() => setSelected({ id: i.id, email: true })}
                    >
                      Create Team Email
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <p className="empty">
                No recurring pattern meets the coaching sample threshold yet.
              </p>
            )}
          </section>
        );
      case "recent":
        return (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Recent interactions</h2>
                <p>People, standards and review context</p>
              </div>
              <Link href="/calls" className="text-link">
                View all interactions
              </Link>
            </div>
            {data.recent.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Interaction</th>
                      <th>Employee / team</th>
                      <th>Scorecard</th>
                      <th>Score / attention</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <Link className="text-link" href={`/calls/${c.id}`}>
                            {c.filename}
                          </Link>
                          {c.is_demo && <small> · Synthetic</small>}
                        </td>
                        <td>
                          {c.employee_id ? (
                            <Link href={`/employees/${c.employee_id}`}>
                              {c.employee_name}
                            </Link>
                          ) : (
                            "Unassigned"
                          )}
                          {c.manager_id && (
                            <small className="block">
                              <Link href={`/employees/${c.manager_id}/team`}>
                                {c.manager_name}
                              </Link>
                            </small>
                          )}
                        </td>
                        <td>
                          {c.rubric_name
                            ? `${c.rubric_name} · v${c.rubric_version}`
                            : "Awaiting evaluation"}
                        </td>
                        <td>
                          {c.score ?? "—"}
                          <small className="block">
                            {c.stale
                              ? "Outdated score"
                              : c.status === "failed"
                                ? "Processing failed"
                                : c.needs_review
                                  ? "Needs review"
                                  : c.score !== null
                                    ? "Reviewed"
                                    : "Processing"}
                          </small>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty">
                Upload an interaction to start your briefing.
              </p>
            )}
          </section>
        );
      case "processing":
        return (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Processing Status</h2>
                <p>
                  {data.awaiting} queued or processing · {data.failed} failed ·{" "}
                  {data.total} interactions in your library
                </p>
              </div>
              <Link href="/batches">View uploads</Link>
            </div>
          </section>
        );
      case "review":
        return (
          <Link href="/calls?needs_review=true" className="review-queue-link">
            Open the supervisor review queue →
          </Link>
        );
      default:
        return null;
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR BUSINESS BRIEFING</div>
          <h1>Dashboard</h1>
          <p>
            Welcome back, {user.name.split(" ")[0]}. See what needs attention
            and choose your next action.
          </p>
        </div>
        <UploadLink />
      </div>
      <div className="briefing-toolbar">
        <DashboardEditor />
        <button
          className="button secondary"
          onClick={() => setRefresh((v) => v + 1)}
        >
          Refresh briefing
        </button>
      </div>
      {error && <ErrorBox message={error} />}
      {!data ? (
        <Loading />
      ) : (
        <div className="dashboard-modules">
          {modules.map((key) => (
            <div key={key}>{content(key)}</div>
          ))}
          {!modules.length && (
            <p className="notice">
              All modules are hidden. Use Customize dashboard to restore them.
            </p>
          )}
        </div>
      )}
      {selected && (
        <IssueDialog
          key={selected.id}
          {...selected}
          onClose={() => {
            setSelected(null);
            setRefresh((v) => v + 1);
          }}
        />
      )}
    </>
  );
}
