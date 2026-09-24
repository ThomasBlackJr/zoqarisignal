"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, date } from "@/lib/api";
import { useDrive } from "./shell";
import { ErrorBox } from "./ui";
type Person = { id: string; name: string; active: boolean };
type Hierarchy = {
  revision: number;
  manager: Person | null;
  linked_user: Person | null;
  direct_reports: Person[];
  history: {
    id: number;
    kind: string;
    previous_manager: Person | null;
    manager: Person | null;
    previous_user: Person | null;
    user: Person | null;
    actor: Person | null;
    changed_at: number;
  }[];
};
export function EmployeeHierarchy({
  id,
  revision,
  onSaved,
  managerEligible,
}: {
  managerEligible: boolean;
  id: string;
  revision: number;
  onSaved: () => Promise<void>;
}) {
  const { user } = useDrive();
  const allowed = ["OWNER", "ADMIN"].includes(user.role);
  const [data, setData] = useState<Hierarchy | null>(null);
  const [users, setUsers] = useState<Person[]>([]);
  const [choice, setChoice] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const h = await api<Hierarchy>(`/employees/${id}/hierarchy`);
        if (alive) setData(h);
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
  }, [id, revision]);
  useEffect(() => {
    let alive = true;
    if (allowed)
      api<{ users: Person[] }>("/team")
        .then((v) => {
          if (alive) setUsers(v.users);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    return () => {
      alive = false;
    };
  }, [allowed]);
  return (
    <section className="panel batch-create">
      <h2>Reporting relationship</h2>
      {error && <ErrorBox message={error} />}{" "}
      {data && (
        <>
          <p>
            Manager:{" "}
            {data.manager ? (
              <Link href={`/employees/${data.manager.id}`}>
                {data.manager.name}
                {!data.manager.active && " (inactive — relationship retained)"}
              </Link>
            ) : (
              "No manager"
            )}
          </p>
          <p>
            {data.direct_reports.length} direct reports. Manager eligibility is
            explicitly configured in employee details; no login is required.
          </p>
          {managerEligible && (
            <Link className="text-link" href={`/employees/${id}/team`}>
              View current team performance →
            </Link>
          )}
          {!!data.direct_reports.length && (
            <ul>
              {data.direct_reports.map((e) => (
                <li key={e.id}>
                  <Link href={`/employees/${e.id}`}>
                    {e.name}
                    {!e.active && " (inactive)"}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <h3>Optional login link</h3>
          <p>
            {data.linked_user
              ? `${data.linked_user.name}${data.linked_user.active ? "" : " (inactive)"}`
              : "No linked login account"}
            . Linking does not change permissions or limit a Manager login to
            this team.
          </p>
          {allowed && (
            <div className="assignment-controls">
              <select
                aria-label="Linked login user"
                value={choice ?? data.linked_user?.id ?? ""}
                onChange={(e) => setChoice(e.target.value)}
              >
                <option value="">No linked user</option>
                {users.map((u) => (
                  <option
                    key={u.id}
                    value={u.id}
                    disabled={!u.active && u.id !== data.linked_user?.id}
                  >
                    {u.name}
                    {!u.active && " (inactive)"}
                  </option>
                ))}
              </select>
              <button
                className="button secondary"
                disabled={saving || choice === null}
                onClick={async () => {
                  setSaving(true);
                  setError("");
                  try {
                    await api(`/employees/${id}/user-link`, {
                      method: "PUT",
                      body: JSON.stringify({
                        user_id: choice || null,
                        revision: data.revision,
                      }),
                    });
                    setChoice(null);
                    await onSaved();
                    setData(await api(`/employees/${id}/hierarchy`));
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setSaving(false);
                  }
                }}
              >
                Save user link
              </button>
            </div>
          )}
          <details className="audit-history">
            <summary>
              Reporting and user-link history ({data.history.length})
            </summary>
            {data.history.map((h) => (
              <p key={h.id}>
                {h.kind === "manager"
                  ? `${h.previous_manager?.name ?? "No manager"} → ${h.manager?.name ?? "No manager"}`
                  : `Login: ${h.previous_user?.name ?? "None"} → ${h.user?.name ?? "None"}`}{" "}
                · {h.actor?.name} · {date(h.changed_at)}
              </p>
            ))}
          </details>
        </>
      )}
    </section>
  );
}
