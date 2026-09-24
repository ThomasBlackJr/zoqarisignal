"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, date } from "@/lib/api";
import { useDrive } from "./shell";
import { ErrorBox } from "./ui";
type Employee = { id: string; name: string; active: boolean };
export function EmployeeAssignment({
  callId,
  employeeId,
  employeeName,
  revision,
  onSaved,
}: {
  callId: string;
  employeeId: string | null;
  employeeName: string | null;
  revision: number;
  onSaved: () => Promise<void>;
}) {
  const { user } = useDrive();
  const editable = ["OWNER", "ADMIN", "MANAGER"].includes(user.role);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [search, setSearch] = useState("");
  const [choice, setChoice] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<
    | {
        id: number;
        previous_employee: string | null;
        employee: string | null;
        actor: string;
        changed_at: number;
      }[]
    | null
  >(null);
  useEffect(() => {
    if (!editable) return;
    let alive = true;
    const timer = setTimeout(() => {
      api<{ items: Employee[] }>(
        "/employees?active=true&q=" + encodeURIComponent(search),
      )
        .then((r) => {
          if (alive) setEmployees(r.items);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    }, 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [search, editable]);
  async function save() {
    setSaving(true);
    setError("");
    try {
      await api("/calls/" + callId + "/assignment", {
        method: "POST",
        body: JSON.stringify({
          employee_id: (choice ?? employeeId) || null,
          revision,
        }),
      });
      await onSaved();
      setChoice(null);
      setHistory(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="panel assignment-panel">
      <div>
        <h2>Assigned employee</h2>
        <p>
          Whose performance should this interaction count toward? This is
          separate from who said each transcript turn.
        </p>
        <strong>
          {employeeId ? (
            <Link href={"/employees/" + employeeId}>{employeeName}</Link>
          ) : (
            "Unassigned"
          )}
        </strong>
      </div>
      {editable && (
        <div className="assignment-controls">
          <input
            aria-label="Search employees for assignment"
            placeholder="Search employees…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            aria-label="Assigned employee"
            value={choice ?? employeeId ?? ""}
            onChange={(e) => setChoice(e.target.value)}
          >
            <option value="">Unassigned</option>
            {employeeId && !employees.some((e) => e.id === employeeId) && (
              <option value={employeeId}>{employeeName} (current)</option>
            )}
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          <button
            className="button secondary"
            disabled={saving || choice === null}
            onClick={save}
          >
            Save assignment
          </button>
        </div>
      )}
      {error && <ErrorBox message={error} />}
      <button
        className="text-link"
        onClick={async () => {
          try {
            setHistory(await api("/calls/" + callId + "/assignments"));
          } catch (e) {
            setError((e as Error).message);
          }
        }}
      >
        Assignment history
      </button>
      {history && (
        <ul>
          {history.length ? (
            history.map((h) => (
              <li key={h.id}>
                {h.previous_employee || "Unassigned"} →{" "}
                {h.employee || "Unassigned"} · {h.actor} · {date(h.changed_at)}
              </li>
            ))
          ) : (
            <li>No assignment changes.</li>
          )}
        </ul>
      )}
    </section>
  );
}
