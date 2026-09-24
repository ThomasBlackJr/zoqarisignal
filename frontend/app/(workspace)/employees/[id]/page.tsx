"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { AdminControls } from "@/components/admin-controls";
import { ManagerPicker } from "@/components/manager-picker";
import { EmployeeHierarchy } from "@/components/employee-hierarchy";
import { api, date } from "@/lib/api";
import { useDrive } from "@/components/shell";
import { ErrorBox, Loading } from "@/components/ui";
type Profile = {
  manager_id: string | null;
  id: string;
  name: string;
  title: string;
  active: boolean;
  manager_eligible: boolean;
  revision: number;
  performance: {
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
      max_score: number;
      average: number;
      sample_count: number;
    }[];
    strengths: { call_id: string; text: string }[];
    coaching_opportunities: { call_id: string; text: string }[];
  };
  recent: {
    id: string;
    filename: string;
    created_at: number;
    status: string;
    score: number | null;
  }[];
};
export default function ProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { user } = useDrive();
  const editable = ["OWNER", "ADMIN", "MANAGER"].includes(user.role);
  const [data, setData] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const p = await api<Profile>("/employees/" + id);
        if (alive) setData(p);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    }
    void load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [id]);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data) return;
    const values = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    try {
      await api("/employees/" + id, {
        method: "PUT",
        body: JSON.stringify({
          name: values.get("name"),
          title: values.get("title"),
          active: values.get("active") === "on",
          revision: data.revision,
          manager_id: values.get("manager_id") || null,
          manager_eligible: values.get("manager_eligible") === "on",
        }),
      });
      setData(await api<Profile>("/employees/" + id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  if (!data)
    return (
      <>
        {error && <ErrorBox message={error} />}
        <Loading />
      </>
    );
  const p = data.performance;
  return (
    <>
      <Link className="back-link" href="/employees">
        ← Employees
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {data.active ? "ACTIVE EMPLOYEE" : "INACTIVE EMPLOYEE"}
          </div>
          <h1>{data.name}</h1>
          <p>{data.title || "Tracked employee"} · Login account not required</p>
        </div>
        <Link className="button secondary" href={"/calls?employee_id=" + id}>
          Assigned interactions
        </Link>
      </div>
      {error && <ErrorBox message={error} />}
      <EmployeeHierarchy
        managerEligible={data.manager_eligible}
        id={id}
        revision={data.revision}
        onSaved={async () => setData(await api<Profile>("/employees/" + id))}
      />
      <div className="metrics">
        <article className="metric">
          <span>Signal Score</span>
          <div className="metric-value">
            {p.signal_score ?? "—"}
            <small>/100</small>
          </div>
          <p>{p.analyzed} current evaluations</p>
        </article>
        <article className="metric">
          <span>Assigned interactions</span>
          <div className="metric-value">{p.interactions}</div>
          <p>{p.stale} outdated evaluations excluded</p>
        </article>
      </div>
      <p className="notice">
        {p.analyzed === 0
          ? "No current evaluated interactions yet. Assign a completed interaction or re-evaluate outdated results."
          : p.limited_sample
            ? "Limited sample: fewer than five current evaluations. Interpret this average with care."
            : "Each assigned interaction contributes its latest, non-stale evaluation once."}{" "}
        Scorecard versions may use different standards; category averages below
        stay separate by version.
      </p>
      <section className="panel batch-create">
        <h2>QA category performance</h2>
        {!p.categories.length ? (
          <p>No current category scores.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Category / scorecard</th>
                  <th>Average</th>
                  <th>Sample</th>
                </tr>
              </thead>
              <tbody>
                {p.categories.map((c) => (
                  <tr key={c.rubric_id + c.key}>
                    <td>
                      {c.name}
                      <small className="batch-note">
                        {c.rubric_name} · Version {c.rubric_version}
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
        )}
      </section>
      <div className="employee-insights">
        {(
          [
            ["Strengths", p.strengths],
            ["Coaching opportunities", p.coaching_opportunities],
          ] as const
        ).map(([title, items]) => (
          <section className="panel batch-create" key={title}>
            <h2>{title}</h2>
            {items.length ? (
              <ul>
                {items.map((item, i) => (
                  <li key={i}>
                    {item.text}{" "}
                    <Link href={"/calls/" + item.call_id}>Review source →</Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No current evaluation insights yet.</p>
            )}
          </section>
        ))}
      </div>
      <section className="panel batch-create">
        <h2>Recent assigned interactions</h2>
        {data.recent.length ? (
          <ul>
            {data.recent.map((c) => (
              <li key={c.id}>
                <Link href={"/calls/" + c.id}>{c.filename}</Link> ·{" "}
                {date(c.created_at)} ·{" "}
                {c.score === null ? "No current score" : c.score + " / 100"}
              </li>
            ))}
          </ul>
        ) : (
          <p>No assigned interactions.</p>
        )}
      </section>
      <AdminControls
        kind="employee"
        id={id}
        revision={data.revision}
        active={data.active}
        onSaved={async () => setData(await api<Profile>("/employees/" + id))}
      />
      {editable && (
        <form
          key={data.revision}
          className="panel employee-create"
          onSubmit={save}
        >
          <h2>Employee details</h2>
          <label>
            Name
            <input
              name="name"
              defaultValue={data.name}
              maxLength={120}
              required
            />
          </label>
          <label>
            Job title
            <input name="title" defaultValue={data.title} maxLength={120} />
          </label>
          <label>
            <input type="checkbox" name="active" defaultChecked={data.active} />{" "}
            Active employee
          </label>
          <label>
            <input
              type="checkbox"
              name="manager_eligible"
              defaultChecked={data.manager_eligible}
            />{" "}
            Can manage employees
          </label>
          <ManagerPicker initial={data.manager_id ?? ""} exclude={id} />
          <p>
            Deactivation retains assignments and history. Inactive employees
            cannot receive new assignments.
          </p>
          <button className="button primary" disabled={saving}>
            Save employee
          </button>
        </form>
      )}
    </>
  );
}
