"use client";
import { useCallback, useEffect, useState } from "react";
import { api, date, User } from "@/lib/api";
import { useDrive } from "@/components/shell";
import { ErrorBox, Loading } from "@/components/ui";

type Invitation = {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: number;
};
export default function TeamPage() {
  const { user } = useDrive();
  const allowed = ["OWNER", "ADMIN"].includes(user.role);
  const [data, setData] = useState<{
    users: (User & { active: boolean })[];
    invitations: Invitation[];
  } | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    setData(await api("/team"));
  }, []);
  useEffect(() => {
    let active = true;
    if (allowed)
      api<{ users: (User & { active: boolean })[]; invitations: Invitation[] }>(
        "/team",
      )
        .then((v) => {
          if (active) setData(v);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [allowed]);
  async function invite(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ mail_delivery: string }>("/invitations", {
        method: "POST",
        body: JSON.stringify({
          email: fields.get("email"),
          role: fields.get("role"),
        }),
      });
      setMessage(
        result.mail_delivery === "local"
          ? "Invitation created. Local development: no email was sent. Open the invite link in the private backend mail outbox. It expires in 48 hours."
          : "Invitation submitted to the configured email service. It expires in 48 hours.",
      );
      form.reset();
      await load();
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
          <div className="eyebrow">ORGANIZATION ACCESS</div>
          <h1>Team &amp; Access</h1>
          <p>
            Invite login users to {user.organization_name}. Tracked employees
            are managed separately.
          </p>
        </div>
      </div>
      {!allowed ? (
        <p className="notice">
          Only owners and administrators can manage access.
        </p>
      ) : (
        <>
          {error && <ErrorBox message={error} />}{" "}
          {message && (
            <p className="success-message" role="status">
              {message}
            </p>
          )}
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Invite a user</h2>
                <p>
                  Joining uses this existing organization and its current access
                  entitlement.
                </p>
              </div>
            </div>
            <form method="post" className="employee-create" onSubmit={invite}>
              <label>
                Work email
                <input name="email" type="email" required maxLength={254} />
              </label>
              <label>
                Role
                <select aria-label="Role" name="role" defaultValue="MANAGER">
                  <option value="ADMIN">Admin</option>
                  <option value="MANAGER">Manager</option>
                  <option value="REVIEWER">Reviewer</option>
                  <option value="EMPLOYEE">Employee</option>
                </select>
              </label>
              <button className="button primary" disabled={saving}>
                {saving ? "Creating invitation…" : "Send invitation"}
              </button>
            </form>
            <p className="panel-foot">
              Admin: team and scorecards. Manager: review and employee
              assignment. Reviewer: quality review. Employee: account access
              only. Invitations cannot grant ownership.
            </p>
          </section>
          {!data ? (
            <Loading />
          ) : (
            <>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Login users</h2>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.users.map((u) => (
                        <tr key={u.id}>
                          <td>{u.name}</td>
                          <td>{u.email}</td>
                          <td>{u.role}</td>
                          <td>
                            {!u.active
                              ? "Inactive"
                              : u.email_verified
                                ? "Verified"
                                : "Unverified"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Recent invitations</h2>
                </div>
                {!data.invitations.length ? (
                  <p className="empty">No invitations yet.</p>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Email</th>
                          <th>Role</th>
                          <th>Status</th>
                          <th>Expires</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.invitations.map((i) => (
                          <tr key={i.id}>
                            <td>{i.email}</td>
                            <td>{i.role}</td>
                            <td>{i.status}</td>
                            <td>{date(i.expires_at)}</td>
                            <td>
                              {i.status === "pending" && (
                                <button
                                  className="text-link"
                                  disabled={saving}
                                  onClick={async () => {
                                    setSaving(true);
                                    try {
                                      await api(`/invitations/${i.id}/revoke`, {
                                        method: "POST",
                                      });
                                      await load();
                                    } catch (e) {
                                      setError((e as Error).message);
                                    } finally {
                                      setSaving(false);
                                    }
                                  }}
                                >
                                  Revoke invitation
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </>
      )}
    </>
  );
}
