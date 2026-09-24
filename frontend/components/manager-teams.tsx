"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { ErrorBox, Loading } from "./ui";
type Performance = {
  interactions: number;
  analyzed: number;
  stale: number;
  signal_score: number | null;
  limited_sample: boolean;
  categories: {
    rubric_id: string;
    rubric_name: string;
    rubric_version: string;
    key: string;
    name: string;
    average: number;
    max_score: number;
    sample_count: number;
  }[];
};
type Person = { id: string; name: string; active: boolean };
type Team = {
  manager: Person;
  direct_reports: number;
  performance: Performance;
  requiring_review: number;
  failed: number;
  members: (Person & { performance: Performance })[];
  recent: {
    id: string;
    filename: string;
    status: string;
    score: number | null;
  }[];
};
export function ManagerTeams({ id }: { id?: string }) {
  const [data, setData] = useState<{ items: Team[]; total: number } | null>(
    null,
  );
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("name");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const value = id
          ? { items: [await api<Team>(`/employees/${id}/team`)], total: 1 }
          : await api<{ items: Team[]; total: number }>(
              `/manager-teams?q=${encodeURIComponent(q)}&sort=${sort}&offset=${offset}`,
            );
        if (alive) {
          setData(value);
          setError("");
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    }
    const delay = setTimeout(load, 200),
      poll = setInterval(load, 5000);
    return () => {
      alive = false;
      clearTimeout(delay);
      clearInterval(poll);
    };
  }, [id, q, sort, offset]);
  const team = id ? data?.items[0] : null;
  return (
    <>
      <Link
        className="back-link"
        href={id ? "/employees/managers" : "/employees"}
      >
        ← {id ? "Manager teams" : "Employees"}
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CURRENT DIRECT REPORTS</div>
          <h1>
            {id
              ? team
                ? `${team.manager.name}’s team`
                : "Manager team"
              : "Manager teams"}
          </h1>
          <p>
            Current reporting relationships. Direct reports only; no historical
            time slicing or indirect reports.
          </p>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      <p className="notice">
        Each interaction contributes its latest eligible Signal Score once,
        including audited overrides. Outdated and superseded evaluations are
        excluded. Moving an employee moves all their currently attributed
        interactions. Inactive people retain their relationships.
      </p>
      {!id && (
        <div className="filters">
          <input
            aria-label="Search manager teams"
            placeholder="Search managers…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
          <select
            aria-label="Sort manager teams"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setOffset(0);
            }}
          >
            <option value="name">Manager name</option>
            <option value="score">Team Signal Score</option>
            <option value="interactions">Interaction count</option>
          </select>
        </div>
      )}
      {!data ? (
        <Loading />
      ) : !id ? (
        <section className="panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Manager</th>
                  <th>Team Signal Score</th>
                  <th>Direct reports</th>
                  <th>Interactions / analyzed</th>
                  <th>Requiring review</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => (
                  <tr key={t.manager.id}>
                    <td>
                      <Link href={`/employees/${t.manager.id}/team`}>
                        {t.manager.name}
                        {!t.manager.active && " (inactive)"}
                      </Link>
                    </td>
                    <td>
                      {t.performance.signal_score ?? "—"}
                      {t.performance.limited_sample && (
                        <small className="batch-note">Limited sample</small>
                      )}
                    </td>
                    <td>{t.direct_reports}</td>
                    <td>
                      {t.performance.interactions} / {t.performance.analyzed}
                    </td>
                    <td>{t.requiring_review}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data.total && (
            <p className="empty">
              No designated managers. Enable Can manage employees in employee
              details to begin.
            </p>
          )}
          <div className="pagination">
            <button
              className="button secondary"
              disabled={!offset}
              onClick={() => setOffset(offset - 50)}
            >
              Previous
            </button>
            <span>{data.total} managers</span>
            <button
              className="button secondary"
              disabled={offset + 50 >= data.total}
              onClick={() => setOffset(offset + 50)}
            >
              Next
            </button>
          </div>
        </section>
      ) : (
        team && (
          <>
            <div className="form-actions">
              <Link className="button secondary" href={`/employees/${id}`}>
                Manager employee profile
              </Link>
              <Link className="button primary" href={`/calls?manager_id=${id}`}>
                View team interactions
              </Link>
            </div>
            {!team.manager.active && (
              <p className="notice">
                This manager is inactive. Existing reports remain included; new
                reporting assignments are blocked.
              </p>
            )}
            <div className="metrics">
              {[
                ["Team Signal Score", team.performance.signal_score ?? "—"],
                ["Direct reports", team.direct_reports],
                ["Interactions analyzed", team.performance.analyzed],
                ["Requiring review", team.requiring_review],
              ].map(([label, value]) => (
                <article className="metric" key={label}>
                  <span>{label}</span>
                  <div className="metric-value">{value}</div>
                </article>
              ))}
            </div>
            <p className="notice">
              {team.performance.stale} outdated evaluations excluded ·{" "}
              {team.failed} processing failures.{" "}
              {team.performance.limited_sample &&
                "Limited sample: fewer than five current evaluations."}{" "}
              Scores use an interaction-weighted average, not an average of
              employee averages.
            </p>
            <section className="panel batch-create">
              <h2>Team members</h2>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Employee</th>
                      <th>Signal Score</th>
                      <th>Interactions</th>
                      <th>Analyzed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {team.members.map((m) => (
                      <tr key={m.id}>
                        <td>
                          <Link href={`/employees/${m.id}`}>
                            {m.name}
                            {!m.active && " (inactive)"}
                          </Link>
                        </td>
                        <td>
                          {m.performance.signal_score ?? "—"}
                          {m.performance.limited_sample && (
                            <small className="batch-note">Limited sample</small>
                          )}
                        </td>
                        <td>{m.performance.interactions}</td>
                        <td>{m.performance.analyzed}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!team.members.length && <p>No direct reports.</p>}
            </section>
            <section className="panel batch-create">
              <h2>Team category performance</h2>
              <p>
                Point averages stay separate by published scorecard version.
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Category / scorecard</th>
                      <th>Average points</th>
                      <th>Sample</th>
                    </tr>
                  </thead>
                  <tbody>
                    {team.performance.categories.map((c) => (
                      <tr key={c.rubric_id + c.key}>
                        <td>
                          {c.name}
                          <small className="batch-note">
                            {c.rubric_name} · {c.rubric_version}
                          </small>
                        </td>
                        <td>
                          {c.average} / {c.max_score}
                        </td>
                        <td>{c.sample_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!team.performance.categories.length && (
                <p>No eligible category scores.</p>
              )}
            </section>
            <section className="panel batch-create">
              <h2>Recent team interactions</h2>
              <ul>
                {team.recent.map((c) => (
                  <li key={c.id}>
                    <Link href={`/calls/${c.id}`}>{c.filename}</Link> ·{" "}
                    {c.status} · {c.score ?? "No current score"}
                  </li>
                ))}
              </ul>
              {!team.recent.length && (
                <p>No assigned interactions for current direct reports.</p>
              )}
            </section>
          </>
        )
      )}
    </>
  );
}
