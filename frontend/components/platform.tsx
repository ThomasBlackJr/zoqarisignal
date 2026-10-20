"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { api, User, date } from "@/lib/api";
import { Brand, ErrorBox, Loading } from "./ui";
import { Appearance } from "./preferences";
import { Dialog } from "./dialog";
import { useResource } from "@/lib/use-platform-resource";
import { OrganizationOwnership } from "./platform-user";

type Organization = {
  id: string;
  name: string;
  suspended: boolean;
  operational_access: boolean;
  subscription_status: string;
  beta_access: { active: boolean; expires_at: number | null } | null;
  usage?: Record<string, number>;
};
type Member = User & { active: boolean };
type Invitation = {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: number;
};
type Employee = {
  id: string;
  name: string;
  manager_eligible: boolean;
  manager_id: string | null;
  active: boolean;
};
type Activity = {
  id: string;
  actor_name: string;
  action: string;
  organization_id: string | null;
  organization_name: string | null;
  reason: string;
  created_at: number;
  details: Record<string, unknown> | null;
};

function ResourceState({ error }: { error?: string }) {
  return error ? <ErrorBox message={error} /> : <Loading />;
}
function Access({ value }: { value: Organization }) {
  return (
    <span>
      {value.suspended
        ? "Suspended"
        : value.operational_access
          ? "Active"
          : "Inactive"}
    </span>
  );
}
function Pager({
  offset,
  count,
  next,
  setOffset,
}: {
  offset: number;
  count: number;
  next?: boolean;
  setOffset: (n: number) => void;
}) {
  return (
    <div className="platform-actions">
      <button
        className="button secondary"
        disabled={!offset}
        onClick={() => setOffset(Math.max(0, offset - 50))}
      >
        Previous
      </button>
      <span>Page {offset / 50 + 1}</span>
      <button
        className="button secondary"
        disabled={!(next ?? count === 50)}
        onClick={() => setOffset(offset + 50)}
      >
        Next
      </button>
    </div>
  );
}

export function PlatformShell({
  name,
  children,
}: {
  name: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [error, setError] = useState("");
  return (
    <div className="app-shell platform-shell">
      <aside className="sidebar">
        <Link href="/platform" aria-label="Zoqari Admin home">
          <Brand />
        </Link>
        <div className="nav-label">PLATFORM</div>
        <nav aria-label="Platform">
          {[
            ["/platform", "Dashboard"],
            ["/platform/organizations", "Organizations"],
            ["/platform/users", "Users"],
            ["/platform/activity", "Activity"],
          ].map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className={
                (
                  href === "/platform"
                    ? pathname === href
                    : pathname.startsWith(href)
                )
                  ? "active"
                  : ""
              }
            >
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Appearance />
          <strong>{name}</strong>
          <small>Platform administrator</small>
          <Link href="/account">Account / customer access</Link>
          <button
            className="button secondary"
            onClick={async () => {
              try {
                await api("/auth/logout", { method: "POST" });
                router.replace("/login");
                router.refresh();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Log out
          </button>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <strong>Zoqari Admin</strong>
          <span>Installation administration</span>
        </header>
        <main className="platform-content">
          {error && <ErrorBox message={error} />}
          {children}
        </main>
      </div>
    </div>
  );
}

export function PlatformDashboard() {
  const result = useResource<Record<string, number>>("/platform/summary");
  return (
    <>
      <div className="eyebrow">ZOQARI ADMIN</div>
      <h1>Platform dashboard</h1>
      <p>Manage organizations and access across this Signal installation.</p>
      {!result?.data ? (
        <ResourceState error={result?.error} />
      ) : (
        <div className="platform-stats">
          {Object.entries(result.data).map(([key, value]) => (
            <div className="panel" key={key}>
              <span>{key === "calls" ? "Retained calls" : key}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      )}
      <section className="panel">
        <h2>Administration</h2>
        <p>
          <Link href="/platform/organizations">
            Manage organizations and beta access
          </Link>
        </p>
        <p>
          <Link href="/platform/users">Find users and memberships</Link>
        </p>
        <p>
          <Link href="/platform/activity">Inspect platform activity</Link>
        </p>
      </section>
      <section className="panel">
        <h2>Integrations</h2>
        <p>Sangoma integration and synchronization are not implemented.</p>
      </section>
    </>
  );
}

export function PlatformOrganizations() {
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const result = useResource<{ total: number; items: Organization[] }>(
    `/platform/organizations?q=${encodeURIComponent(q)}&offset=${offset}`,
    revision,
  );
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  return (
    <>
      <div className="eyebrow">PLATFORM</div>
      <h1>Organizations</h1>
      <div className="platform-actions">
        <label>
          Search organizations
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <button
          className="button primary"
          onClick={() => {
            setError("");
            setCreating(true);
          }}
        >
          Create organization
        </button>
        <button
          className="button secondary"
          onClick={() => setRevision((v) => v + 1)}
        >
          Refresh
        </button>
      </div>
      {!result?.data ? (
        <ResourceState error={result?.error} />
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Organization</th>
                  <th>Access</th>
                  <th>Beta expiration</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((v) => (
                  <tr key={v.id}>
                    <td>
                      <Link href={`/platform/organizations/${v.id}`}>
                        {v.name}
                      </Link>
                    </td>
                    <td>
                      <Access value={v} />
                    </td>
                    <td>
                      {v.beta_access?.active
                        ? v.beta_access.expires_at
                          ? date(v.beta_access.expires_at)
                          : "No expiration"
                        : "No active grant"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!result.data.items.length && <p>No organizations found.</p>}
          </div>
          <Pager
            offset={offset}
            count={result.data.items.length}
            next={offset + 50 < result.data.total}
            setOffset={setOffset}
          />
        </>
      )}
      {creating && (
        <Dialog
          title="Create organization"
          onClose={() => {
            if (!pending) setCreating(false);
          }}
        >
          <p>
            The organization starts inactive. Invite its Owner and grant access
            separately.
          </p>
          {error && <ErrorBox message={error} />}
          <form
            className="account-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setPending(true);
              setError("");
              const f = new FormData(e.currentTarget);
              try {
                const v = await api<Organization>("/platform/organizations", {
                  method: "POST",
                  body: JSON.stringify({
                    name: f.get("name"),
                    reason: f.get("reason"),
                  }),
                });
                router.push(`/platform/organizations/${v.id}`);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setPending(false);
              }
            }}
          >
            <label>
              Organization name
              <input name="name" required maxLength={120} />
            </label>
            <label>
              Reason
              <input name="reason" required maxLength={500} />
            </label>
            <button className="button primary" disabled={pending}>
              Create
            </button>
          </form>
        </Dialog>
      )}
    </>
  );
}

function MemberTable({ items }: { items: Member[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Organization</th>
            <th>Customer role</th>
            <th>Account</th>
          </tr>
        </thead>
        <tbody>
          {items.map((u) => (
            <tr key={u.id}>
              <td>
                <Link href={`/platform/users/${u.id}`}>{u.name}</Link>
                {u.is_platform_admin && (
                  <small> · Platform administrator</small>
                )}
              </td>
              <td>{u.email}</td>
              <td>
                {u.organization_id ? (
                  <Link href={`/platform/organizations/${u.organization_id}`}>
                    {u.organization_name}
                  </Link>
                ) : (
                  "No organization"
                )}
              </td>
              <td>{u.organization_id ? u.role : "No customer membership"}</td>
              <td>
                {!u.active
                  ? "Disabled"
                  : u.email_verified
                    ? "Verified"
                    : "Unverified"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && <p>No users found.</p>}
    </div>
  );
}

export function PlatformUsers() {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [org, setOrg] = useState("");
  const [offset, setOffset] = useState(0);
  const orgs = useResource<{ items: Organization[] }>(
    `/platform/organizations?q=${encodeURIComponent(org)}`,
  );
  const [organizationId, setOrganizationId] = useState("");
  const result = useResource<{ total: number; items: Member[] }>(
    `/platform/users?q=${encodeURIComponent(q)}&offset=${offset}${status ? `&status=${status}` : ""}${role ? `&role=${role}` : ""}${organizationId ? `&organization_id=${encodeURIComponent(organizationId)}` : ""}`,
  );
  return (
    <>
      <div className="eyebrow">PLATFORM</div>
      <h1>Users</h1>
      <Link className="button primary" href="/platform/users/new">
        Create account
      </Link>
      <p>
        Login accounts and customer membership. Tracked employees are listed
        within each organization.
      </p>
      <div className="platform-actions">
        <label>
          Account status
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
            <option value="unverified">Unverified</option>
          </select>
        </label>
        <label>
          Search users
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          Customer role
          <select
            value={role}
            onChange={(e) => {
              setRole(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All roles</option>
            {[
              "OWNER",
              "ADMIN",
              "MANAGER",
              "REVIEWER",
              "EMPLOYEE",
              "SUPERVISOR",
            ].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <label>
          Find organization
          <input
            value={org}
            onChange={(e) => {
              setOrg(e.target.value);
              setOrganizationId("");
              setOffset(0);
            }}
          />
        </label>
        <label>
          Organization
          <select
            value={organizationId}
            onChange={(e) => {
              setOrganizationId(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All organizations</option>
            {orgs.data?.items.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!result?.data ? (
        <ResourceState error={result?.error} />
      ) : (
        <>
          <MemberTable items={result.data.items} />
          <Pager
            offset={offset}
            count={result.data.items.length}
            next={offset + 50 < result.data.total}
            setOffset={setOffset}
          />
        </>
      )}
    </>
  );
}

export function PlatformActivity() {
  const [offset, setOffset] = useState(0);
  const result = useResource<{ items: Activity[] }>(
    `/platform/activity?offset=${offset}`,
  );
  return (
    <>
      <div className="eyebrow">PLATFORM</div>
      <h1>Activity</h1>
      <p>
        Audited platform actions, inspections, access changes and invitations.
      </p>
      {!result?.data ? (
        <ResourceState error={result?.error} />
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Target</th>
                  <th>Reason / details</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((a) => (
                  <tr key={a.id}>
                    <td>{date(a.created_at)}</td>
                    <td>{a.actor_name}</td>
                    <td>{a.action}</td>
                    <td>
                      {typeof a.details?.user_id === "string" && (
                        <p>
                          <Link href={`/platform/users/${a.details.user_id}`}>
                            Account details
                          </Link>
                        </p>
                      )}
                      {a.organization_id ? (
                        <Link
                          href={`/platform/organizations/${a.organization_id}`}
                        >
                          {a.organization_name}
                        </Link>
                      ) : (
                        "Platform"
                      )}
                    </td>
                    <td>
                      {a.reason}
                      {a.details && (
                        <pre>{JSON.stringify(a.details, null, 2)}</pre>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!result.data.items.length && <p>No activity yet.</p>}
          </div>
          <Pager
            offset={offset}
            count={result.data.items.length}
            setOffset={setOffset}
          />
        </>
      )}
    </>
  );
}

export function PlatformOrganization({ id }: { id: string }) {
  const path = `/platform/organizations/${encodeURIComponent(id)}`;
  const [revision, setRevision] = useState(0);
  const [memberOffset, setMemberOffset] = useState(0);
  const [employeeOffset, setEmployeeOffset] = useState(0);
  const [inviteOffset, setInviteOffset] = useState(0);
  const result = useResource<Organization>(path, revision);
  const members = useResource<{ items: Member[] }>(
    `${path}/members?offset=${memberOffset}`,
    revision,
  );
  const employees = useResource<{ total: number; items: Employee[] }>(
    `${path}/employees?offset=${employeeOffset}`,
    revision,
  );
  const invitations = useResource<{ items: Invitation[] }>(
    `${path}/invitations?offset=${inviteOffset}`,
    revision,
  );
  const [action, setAction] = useState("");
  const [invitationId, setInvitationId] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const value = result?.data;
  function choose(action: string, invitationId = "") {
    setError("");
    setAction(action);
    setInvitationId(invitationId);
  }
  if (!value) return <ResourceState error={result?.error} />;
  return (
    <>
      <Link href="/platform/organizations">Organizations</Link>
      <h1>{value.name}</h1>
      <OrganizationOwnership
        id={id}
        changed={() => setRevision((v) => v + 1)}
      />
      <p>
        Access: <Access value={value} /> · Subscription:{" "}
        {value.subscription_status}
      </p>
      {message && <p role="status">{message}</p>}
      <section className="panel">
        <h2>Organization access</h2>
        <p>
          Beta grant: {value.beta_access?.active ? "Granted" : "Not granted"}.
          Expiration:{" "}
          {value.beta_access?.expires_at
            ? date(value.beta_access.expires_at)
            : "None"}
          . Expired grants do not provide access.
        </p>
        <div className="platform-actions">
          <button
            className="button primary"
            onClick={() => choose("Grant beta access")}
          >
            Grant beta access
          </button>
          <button
            className="button secondary"
            disabled={!value.beta_access?.active}
            onClick={() => choose("Revoke beta access")}
          >
            Revoke beta access
          </button>
          <button
            className="button secondary"
            onClick={() =>
              choose(
                value.suspended
                  ? "Reactivate organization"
                  : "Suspend organization",
              )
            }
          >
            {value.suspended
              ? "Reactivate organization"
              : "Suspend organization"}
          </button>
        </div>
      </section>
      <section className="panel">
        <h2>Usage</h2>
        <p>
          Current retained records; historical evaluations and completed review
          records are counted separately.
        </p>
        <div className="platform-stats">
          {Object.entries(value.usage || {}).map(([k, v]) => (
            <div key={k}>
              <span>{k.replaceAll("_", " ")}</span>
              <strong>{v}</strong>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <h2>Organization users</h2>
        {members.data ? (
          <>
            <MemberTable items={members.data.items} />
            <Pager
              offset={memberOffset}
              count={members.data.items.length}
              setOffset={setMemberOffset}
            />
          </>
        ) : (
          <ResourceState error={members.error} />
        )}
      </section>
      <section className="panel">
        <h2>Tracked employees</h2>
        <p>Reporting designation does not grant login permissions.</p>
        {employees.data ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Designation</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.data.items.map((e) => (
                    <tr key={e.id}>
                      <td>{e.name}</td>
                      <td>{e.manager_eligible ? "Manager" : "Employee"}</td>
                      <td>{e.active ? "Active" : "Archived"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!employees.data.items.length && <p>No tracked employees.</p>}
            </div>
            <Pager
              offset={employeeOffset}
              count={employees.data.items.length}
              next={employeeOffset + 50 < employees.data.total}
              setOffset={setEmployeeOffset}
            />
          </>
        ) : (
          <ResourceState error={employees.error} />
        )}
      </section>
      <section className="panel">
        <h2>Invitations</h2>
        <button
          className="button primary"
          onClick={() => choose("Invite user")}
        >
          Invite user
        </button>
        {invitations.data ? (
          <>
            <div className="table-scroll">
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
                  {invitations.data.items.map((i) => (
                    <tr key={i.id}>
                      <td>{i.email}</td>
                      <td>{i.role}</td>
                      <td>{i.status}</td>
                      <td>{date(i.expires_at)}</td>
                      <td>
                        {i.status === "pending" && (
                          <button
                            className="button secondary"
                            onClick={() => choose("Revoke invitation", i.id)}
                          >
                            Revoke invitation for {i.email}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!invitations.data.items.length && <p>No invitations.</p>}
            </div>
            <Pager
              offset={inviteOffset}
              count={invitations.data.items.length}
              setOffset={setInviteOffset}
            />
          </>
        ) : (
          <ResourceState error={invitations.error} />
        )}
      </section>
      <section className="panel">
        <h2>Integrations</h2>
        <p>Sangoma integration and synchronization are not implemented.</p>
      </section>
      {action && (
        <Dialog
          title={action}
          onClose={() => {
            if (!pending) setAction("");
          }}
        >
          {error && <ErrorBox message={error} />}
          <p>
            Changes apply to {value.name} and are recorded in platform activity.
            Revoking beta access preserves other valid entitlements. Suspension
            blocks operational access.
          </p>
          <form
            className="account-form"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              setPending(true);
              setError("");
              try {
                let endpoint = path;
                let method = "PUT";
                const body: Record<string, unknown> = {
                  reason: f.get("reason"),
                };
                if (action === "Invite user") {
                  endpoint += "/invitations";
                  method = "POST";
                  body.email = f.get("email");
                  body.role = f.get("role");
                } else if (action === "Revoke invitation") {
                  endpoint += `/invitations/${encodeURIComponent(invitationId)}/revoke`;
                  method = "POST";
                } else if (action === "Grant beta access") {
                  endpoint += "/beta-access";
                  const expiration = f.get("expiration");
                  body.expires_at = expiration
                    ? new Date(String(expiration)).getTime() / 1000
                    : null;
                } else if (action === "Revoke beta access") {
                  endpoint += "/beta-access";
                  method = "DELETE";
                } else {
                  endpoint += "/suspension";
                  body.suspended = action === "Suspend organization";
                }
                await api(endpoint, { method, body: JSON.stringify(body) });
                setAction("");
                setMessage(`${action} completed.`);
                setRevision((v) => v + 1);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setPending(false);
              }
            }}
          >
            {action === "Invite user" && (
              <>
                <label>
                  Email
                  <input name="email" type="email" required maxLength={254} />
                </label>
                <label>
                  Role
                  <select name="role" defaultValue="EMPLOYEE">
                    {["OWNER", "ADMIN", "MANAGER", "REVIEWER", "EMPLOYEE"].map(
                      (r) => (
                        <option key={r}>{r}</option>
                      ),
                    )}
                  </select>
                </label>
              </>
            )}
            {action === "Grant beta access" && (
              <label>
                Expiration (your local time, optional)
                <input name="expiration" type="datetime-local" />
              </label>
            )}
            <label>
              Reason
              <input name="reason" required maxLength={500} />
            </label>
            <button className="button primary" disabled={pending}>
              {pending ? "Saving..." : "Confirm"}
            </button>
          </form>
        </Dialog>
      )}
    </>
  );
}
