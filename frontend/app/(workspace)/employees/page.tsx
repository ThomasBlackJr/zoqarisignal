"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ManagerPicker } from "@/components/manager-picker";
import { api } from "@/lib/api";
import { useDrive } from "@/components/shell";
import { ErrorBox, Loading } from "@/components/ui";
type Employee = {
  id: string;
  name: string;
  title: string;
  active: boolean;
  manager_eligible: boolean;
  revision: number;
};
export default function EmployeesPage() {
  const { user } = useDrive();
  const editable = ["OWNER", "ADMIN", "MANAGER"].includes(user.role);
  const [q, setQ] = useState("");
  const [active, setActive] = useState("true");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: Employee[]; total: number } | null>(
    null,
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      api<{ items: Employee[]; total: number }>(
        "/employees?q=" +
          encodeURIComponent(q) +
          "&offset=" +
          offset +
          (active ? "&active=" + active : ""),
      )
        .then((r) => {
          if (alive) setData(r);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    }, 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [q, active, offset, reload]);
  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setSaving(true);
    setError("");
    try {
      await api("/employees", {
        method: "POST",
        body: JSON.stringify({
          name: fields.get("name"),
          title: fields.get("title"),
          manager_id: fields.get("manager_id") || null,
          manager_eligible: fields.get("manager_eligible") === "on",
        }),
      });
      form.reset();
      setReload((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">TEAM PERFORMANCE</div>
          <h1>Employees</h1>
          <p>
            Track the people whose interactions you evaluate. Employees do not
            need Signal login accounts.
          </p>
        </div>
        <Link className="button secondary" href="/employees/managers">
          Manager teams
        </Link>
      </div>
      {editable && (
        <Link className="button secondary" href="/employees/import">
          Import CSV / XLSX
        </Link>
      )}
      {error && <ErrorBox message={error} />}
      {editable && (
        <form key={reload} className="panel employee-create" onSubmit={create}>
          <h2>Add employee</h2>
          <label>
            Name
            <input name="name" required maxLength={120} />
          </label>
          <label>
            Job title
            <input name="title" maxLength={120} />
          </label>
          <label>
            <input type="checkbox" name="manager_eligible" /> Can manage
            employees
          </label>
          <ManagerPicker />
          <p>
            Only active employees explicitly designated as Managers can receive
            new direct reports. Login roles do not determine eligibility.
          </p>
          <button className="button primary" disabled={saving}>
            Create employee
          </button>
        </form>
      )}
      <section className="panel">
        <div className="filters">
          <input
            aria-label="Search employees"
            value={q}
            placeholder="Search employees…"
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
          <select
            aria-label="Employee status"
            value={active}
            onChange={(e) => {
              setActive(e.target.value);
              setOffset(0);
            }}
          >
            <option value="true">Active employees</option>
            <option value="false">Inactive employees</option>
            <option value="">All employees</option>
          </select>
        </div>
        {!data ? (
          <Loading />
        ) : !data.items.length ? (
          <p className="batch-create">
            No employees match. Add an employee to begin assigning interactions.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Job title</th>
                  <th>Employee type</th>
                  <th>Status</th>
                  <th>Performance</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id}>
                    <td>
                      <Link href={"/employees/" + e.id}>
                        <strong>{e.name}</strong>
                      </Link>
                    </td>
                    <td>{e.title || "—"}</td>
                    <td>{e.manager_eligible ? "Manager" : "Employee"}</td>
                    <td>{e.active ? "Active" : "Inactive"}</td>
                    <td>
                      <Link href={"/employees/" + e.id}>View employee →</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="batch-pagination">
          <button
            className="button secondary"
            disabled={!offset}
            onClick={() => setOffset((v) => Math.max(0, v - 100))}
          >
            Previous
          </button>
          <span>{data?.total ?? 0} employees</span>
          <button
            className="button secondary"
            disabled={!data || offset + 100 >= data.total}
            onClick={() => setOffset((v) => v + 100)}
          >
            Next
          </button>
        </div>
      </section>
    </>
  );
}
