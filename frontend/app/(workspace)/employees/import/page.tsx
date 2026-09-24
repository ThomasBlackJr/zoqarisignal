"use client";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
type Preview = {
  id: string;
  total: number;
  ready: number;
  warnings: number;
  errors: number;
  rows: {
    row: number;
    name: string;
    email: string | null;
    external_id: string | null;
    manager: string;
    errors: string[];
    warnings: string[];
  }[];
};
export default function ImportPage() {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function upload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    setPreview(null);
    try {
      setPreview(
        await api<Preview>("/employee-imports/preview", {
          method: "POST",
          body: new FormData(e.currentTarget),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ created: number }>(
        `/employee-imports/${preview.id}/commit`,
        { method: "POST" },
      );
      setMessage(
        `${result.created} employees imported. No login accounts were created.`,
      );
      setPreview(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">EMPLOYEES</div>
          <h1>Import employees</h1>
          <p>
            Preview your CSV or XLSX before creating records. Existing employees
            are never overwritten.
          </p>
        </div>
        <Link href="/employees">Back to employees</Link>
      </div>
      {error && <ErrorBox message={error} />}{" "}
      {message && <p role="status">{message}</p>}
      <section className="panel dialog-content">
        <a
          className="button secondary"
          href="/api/employee-imports/template.csv"
          download
        >
          Download CSV template
        </a>
        <p>
          First Name and Last Name are required. Optional: Email, Employee ID,
          Manager, Manager Eligible. Manager accepts an employee ID or email
          from this file or your organization; row order does not matter. Use
          yes/no for Manager Eligible. IDs are case insensitive. One sheet, up
          to 1,000 rows and 2 MB.
        </p>
        <form className="account-form" onSubmit={upload}>
          <label htmlFor="employee-file">Employee CSV or XLSX</label>
          <input
            id="employee-file"
            type="file"
            name="file"
            accept=".csv,.xlsx"
            required
            disabled={busy}
          />
          <button className="button primary" disabled={busy}>
            {busy ? "Working�" : "Preview import"}
          </button>
        </form>
      </section>
      {preview && (
        <section className="panel dialog-content">
          <h2>Import preview</h2>
          <p>
            {preview.total} rows � {preview.ready} ready � {preview.warnings}{" "}
            with warnings � {preview.errors} with errors
          </p>
          <p>
            Review all warnings. Fix errors in the file and upload it again.
            Preview expires in 30 minutes; committing rechecks the current
            employee directory.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Employee</th>
                  <th>ID / email</th>
                  <th>Manager</th>
                  <th>Validation</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.row}>
                    <td>{row.row}</td>
                    <td>{row.name}</td>
                    <td>
                      {row.external_id || "�"}
                      <br />
                      {row.email}
                    </td>
                    <td>{row.manager || "�"}</td>
                    <td>
                      {[...row.errors, ...row.warnings].join("; ") || "Ready"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            className="button primary"
            disabled={busy || preview.errors > 0}
            onClick={commit}
          >
            Confirm and import {preview.ready} employees
          </button>
        </section>
      )}
    </>
  );
}
