"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, date, User } from "@/lib/api";
import { Dialog } from "@/components/dialog";
import { AccountFrame } from "@/components/account-frame";
import { ErrorBox, Loading } from "@/components/ui";
import "./platform.css";

type Event = {
  action: string;
  actor: string;
  reason: string | null;
  created_at: number;
  expires_at?: number | null;
};
type Person = User & {
  active: boolean;
  created_at: number | null;
  last_login_at: number | null;
  events?: Event[];
};
type Organization = {
  id: string;
  name: string;
  suspended: boolean;
  member_count: number;
  operational_access: boolean;
  pilot_approved: boolean;
  beta_access: boolean;
  signal_access: string;
  pilot_expires_at: number | null;
  owners: { name: string; email: string; active: boolean }[];
  users?: Person[];
  events?: Event[];
  pilot_history?: Event[];
};

function History({ rows = [] }: { rows?: Event[] }) {
  return (
    <div className="platform-history">
      {rows.length ? (
        rows.map((e, i) => (
          <article key={i}>
            <strong>{e.action.replaceAll("_", " ")}</strong>
            <p>
              {date(e.created_at)} · {e.actor}
            </p>
            {e.reason && <p>{e.reason}</p>}
            {e.expires_at && <p>Expiry: {date(e.expires_at)}</p>}
          </article>
        ))
      ) : (
        <p>
          No recorded events. Older activity may predate lifecycle auditing.
        </p>
      )}
    </div>
  );
}

export default function PlatformPage() {
  const [authorized, setAuthorized] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [users, setUsers] = useState<Person[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [user, setUser] = useState<Person | null>(null);
  const [org, setOrg] = useState<Organization | null>(null);
  const [query, setQuery] = useState("");
  const [orgQuery, setOrgQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [orgOffset, setOrgOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [orgTotal, setOrgTotal] = useState(0);
  const [reason, setReason] = useState("");
  const [expiry, setExpiry] = useState("");
  const [busy, setBusy] = useState(false);
  const [betaAction, setBetaAction] = useState<"grant" | "expiry" | null>(null);
  useEffect(() => {
    api("/platform/session")
      .then(() => setAuthorized(true))
      .catch((e) => {
        setError(e.message);
        setBlocked(true);
      });
  }, []);
  useEffect(() => {
    if (!authorized) return;
    let active = true;
    const timer = setTimeout(() => {
      api<{ items: Person[]; total: number }>(
        `/platform/users?q=${encodeURIComponent(query)}&offset=${offset}`,
      )
        .then((v) => {
          if (active) {
            setUsers(v.items);
            setTotal(v.total);
          }
        })
        .catch((e) => setError(e.message));
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [authorized, query, offset]);
  useEffect(() => {
    if (!authorized) return;
    let active = true;
    const timer = setTimeout(() => {
      api<{ items: Organization[]; total: number }>(
        `/platform/organizations?q=${encodeURIComponent(orgQuery)}&offset=${orgOffset}`,
      )
        .then((v) => {
          if (active) {
            setOrgs(v.items);
            setOrgTotal(v.total);
          }
        })
        .catch((e) => setError(e.message));
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [authorized, orgQuery, orgOffset]);
  async function selectUser(id: string) {
    try {
      setBetaAction(null);
      setUser(await api<Person>(`/platform/users/${id}`));
      setOrg(null);
      setReason("");
      setMessage("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function selectOrg(id: string) {
    try {
      setBetaAction(null);
      const value = await api<Organization>(`/platform/organizations/${id}`);
      setOrg(value);
      setUser(null);
      setReason("");
      setMessage("");
      setExpiry(
        value.pilot_expires_at
          ? new Date(value.pilot_expires_at * 1000).toISOString().slice(0, 16)
          : "",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function mutate(path: string, extra: object = {}) {
    if (
      !reason.trim() &&
      !("reason" in extra && String(extra.reason).trim()) &&
      !path.includes("/pilot")
    ) {
      setError("Enter a reason for this action.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ message?: string }>(path, {
        method: "POST",
        body: JSON.stringify({ reason, ...extra }),
      });
      if (user) setUser(await api<Person>(`/platform/users/${user.id}`));
      if (org) {
        const fresh = await api<Organization>(
          `/platform/organizations/${org.id}`,
        );
        setOrg(fresh);
        setOrgs((rows) =>
          rows.map((row) => (row.id === fresh.id ? fresh : row)),
        );
      }
      setMessage(
        result.message ||
          "Account status updated. Existing sessions were revoked.",
      );
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  const details = (
    <>
      <label htmlFor="action-reason">Reason for administrative action</label>
      <textarea
        id="action-reason"
        maxLength={500}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        required
      />
      <p className="muted">
        Every change is attributed to your signed-in administrator account.
        Never enter passwords or verification codes here.
      </p>
    </>
  );
  return (
    <AccountFrame>
      <div className="platform-console">
        <h2>Platform administration</h2>
        <p>
          Privileged account and organization controls. Customer workspace
          permissions remain separate.
        </p>
        <p>
          <Link href="/account">My account</Link>
        </p>
        {error && <ErrorBox message={error} />}
        {message && <p role="status">{message}</p>}
        {!authorized ? (
          blocked ? (
            <p>
              Access is restricted to explicitly authorized, verified platform
              administrators.
            </p>
          ) : (
            <Loading />
          )
        ) : (
          <>
            <section aria-label="Organization search">
              <h3>Organizations</h3>
              <label htmlFor="org-search">Search organizations</label>
              <input
                id="org-search"
                maxLength={120}
                value={orgQuery}
                onChange={(e) => {
                  setOrgQuery(e.target.value);
                  setOrgOffset(0);
                }}
              />
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Organization</th>
                      <th>Members</th>
                      <th>Status</th>
                      <th>Signal Access</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orgs.map((o) => (
                      <tr key={o.id}>
                        <td>
                          <button
                            className="button secondary"
                            onClick={() => selectOrg(o.id)}
                          >
                            {o.name}
                          </button>
                        </td>
                        <td>{o.member_count}</td>
                        <td>{o.suspended ? "Paused" : "Active"}</td>
                        <td>{o.signal_access}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p>{orgTotal} matching organizations</p>
              <button
                disabled={orgOffset === 0}
                onClick={() => setOrgOffset(Math.max(0, orgOffset - 25))}
              >
                Previous organizations
              </button>
              <button
                disabled={orgOffset + 25 >= orgTotal}
                onClick={() => setOrgOffset(orgOffset + 25)}
              >
                Next organizations
              </button>
            </section>
            <section aria-label="User search">
              <h3>Users</h3>
              <label htmlFor="user-search">Search users</label>
              <input
                id="user-search"
                maxLength={120}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setOffset(0);
                }}
              />
              <ul>
                {users.map((u) => (
                  <li key={u.id}>
                    <button
                      className="button secondary"
                      onClick={() => selectUser(u.id)}
                    >
                      {u.name} · {u.email}
                    </button>
                  </li>
                ))}
              </ul>
              <p>{total} matching users</p>
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 25))}
              >
                Previous users
              </button>
              <button
                disabled={offset + 25 >= total}
                onClick={() => setOffset(offset + 25)}
              >
                Next users
              </button>
            </section>
            {user && (
              <section aria-label="User details">
                <h3>{user.name}</h3>
                <p>{user.email}</p>
                <p>
                  {user.active ? "Active" : "Inactive"} ·{" "}
                  {user.email_verified ? "Verified" : "Unverified"} ·{" "}
                  {user.role}
                </p>
                <p>
                  Organization: {user.organization_name || "Not joined yet"}
                </p>
                <p>
                  Created:{" "}
                  {user.created_at
                    ? date(user.created_at)
                    : "Not recorded for this older account"}
                </p>
                <p>
                  Last sign-in:{" "}
                  {user.last_login_at
                    ? date(user.last_login_at)
                    : "Not recorded"}
                </p>
                {details}
                <div className="platform-actions">
                  {!user.is_platform_admin && (
                    <button
                      className="button secondary"
                      disabled={busy}
                      onClick={() =>
                        mutate(`/platform/users/${user.id}/status`, {
                          active: !user.active,
                        })
                      }
                    >
                      {user.active ? "Deactivate account" : "Activate account"}
                    </button>
                  )}
                  {user.active && !user.email_verified && (
                    <button
                      className="button secondary"
                      disabled={busy}
                      onClick={() =>
                        mutate(`/platform/users/${user.id}/verification`)
                      }
                    >
                      Send verification code
                    </button>
                  )}
                  {user.active && (
                    <button
                      className="button secondary"
                      disabled={busy}
                      onClick={() =>
                        mutate(`/platform/users/${user.id}/password-reset`)
                      }
                    >
                      Send password reset
                    </button>
                  )}
                </div>
                <h4>Account events</h4>
                <History rows={user.events} />
              </section>
            )}
            {org && (
              <section aria-label="Organization details">
                <h3>{org.name}</h3>
                <p>Status: {org.suspended ? "Paused" : "Active"}</p>
                <h4>SIGNAL ACCESS</h4>
                <p>
                  {org.beta_access
                    ? "Beta Access"
                    : org.operational_access
                      ? "Signal Access"
                      : "No Beta Access"}
                </p>
                <p>
                  All current and future members inherit organization access.
                  Their existing role permissions still apply.
                </p>
                <p>
                  Expiration:{" "}
                  {org.pilot_expires_at ? date(org.pilot_expires_at) : "Never"}
                </p>
                <p>
                  Owner:{" "}
                  {org.owners
                    .map(
                      (o) =>
                        `${o.name} (${o.email})${o.active ? "" : " — inactive"}`,
                    )
                    .join(", ") || "No Owner recorded"}
                </p>
                <p>{org.member_count} members</p>
                <div className="platform-actions">
                  {!org.beta_access && (
                    <button
                      className="button primary"
                      disabled={busy}
                      onClick={() => setBetaAction("grant")}
                    >
                      Grant Beta Access
                    </button>
                  )}
                  {org.pilot_approved && (
                    <>
                      <button
                        className="button secondary"
                        disabled={busy}
                        onClick={() =>
                          void mutate(
                            `/platform/organizations/${org.id}/pilot/revoke`,
                          )
                        }
                      >
                        Revoke Beta Access
                      </button>
                      <button
                        className="button secondary"
                        disabled={busy}
                        onClick={() => setBetaAction("expiry")}
                      >
                        Change Expiration
                      </button>
                    </>
                  )}
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() =>
                      void mutate(
                        `/platform/organizations/${org.id}/suspension`,
                        {
                          suspended: !org.suspended,
                          reason:
                            reason.trim() ||
                            "Platform administrator updated organization status",
                        },
                      )
                    }
                  >
                    {org.suspended
                      ? "Resume organization"
                      : "Pause organization"}
                  </button>
                </div>
                {betaAction && (
                  <Dialog
                    title={
                      betaAction === "grant"
                        ? `Grant Beta Access to ${org.name}?`
                        : `Change Beta Expiration for ${org.name}`
                    }
                    onClose={() => setBetaAction(null)}
                  >
                    <p>
                      This enables Signal call analysis for all current and
                      future members of this organization, according to their
                      role permissions.
                    </p>
                    {error && <ErrorBox message={error} />}
                    <label htmlFor="beta-expiry-mode">Expiration</label>
                    <select
                      id="beta-expiry-mode"
                      value={expiry ? "date" : "never"}
                      onChange={(e) =>
                        setExpiry(
                          e.target.value === "never"
                            ? ""
                            : new Date(Date.now() + 30 * 86400000)
                                .toISOString()
                                .slice(0, 16),
                        )
                      }
                    >
                      <option value="never">Never</option>
                      <option value="date">Specific date</option>
                    </select>
                    {expiry && (
                      <>
                        <label htmlFor="beta-expiration">
                          Beta expiration (UTC)
                        </label>
                        <input
                          id="beta-expiration"
                          type="datetime-local"
                          value={expiry}
                          onChange={(e) => setExpiry(e.target.value)}
                        />
                      </>
                    )}
                    <label htmlFor="beta-reason">Reason (optional)</label>
                    <textarea
                      id="beta-reason"
                      maxLength={500}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                    <div className="platform-actions">
                      <button
                        disabled={busy}
                        onClick={() => setBetaAction(null)}
                      >
                        Cancel
                      </button>
                      <button
                        className="button primary"
                        disabled={busy}
                        onClick={async () => {
                          const end = expiry
                            ? Date.parse(expiry + "Z") / 1000
                            : null;
                          if (
                            end !== null &&
                            (!Number.isFinite(end) || end <= Date.now() / 1000)
                          ) {
                            setError("Choose a future UTC expiration.");
                            return;
                          }
                          if (
                            await mutate(
                              `/platform/organizations/${org.id}/pilot`,
                              { expires_at: end },
                            )
                          )
                            setBetaAction(null);
                        }}
                      >
                        {betaAction === "grant"
                          ? "Grant Access"
                          : "Save Expiration"}
                      </button>
                    </div>
                  </Dialog>
                )}
                <h4>Organization members</h4>
                <ul>
                  {org.users?.map((u) => (
                    <li key={u.id}>
                      <button
                        className="button secondary"
                        onClick={() => selectUser(u.id)}
                      >
                        {u.name} · {u.email} · {u.role}
                      </button>
                    </li>
                  ))}
                </ul>
                <h4>Signal access audit history</h4>
                <History rows={org.pilot_history} />
                <h4>Organization events</h4>
                <History rows={org.events} />
              </section>
            )}
          </>
        )}
      </div>
    </AccountFrame>
  );
}
