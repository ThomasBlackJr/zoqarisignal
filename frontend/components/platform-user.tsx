"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, date, User } from "@/lib/api";
import { useResource } from "@/lib/use-platform-resource";
import { Dialog } from "./dialog";
import { ErrorBox, Loading } from "./ui";

type Account = User & {
  active: boolean;
  revision: number;
  first_name: string | null;
  last_name: string | null;
  operational_access: boolean;
  permissions: string[];
  created_at: number | null;
  updated_at: number | null;
  deactivated_at: number | null;
  last_session_at: number | null;
  employee: {
    id: string;
    name: string;
    revision: number;
    manager_id: string | null;
    manager_name: string | null;
  } | null;
  activity: {
    id: string;
    action: string;
    actor_id: string;
    created_at: number;
    reason: string;
    details: Record<string, unknown>;
  }[];
};
type Employee = {
  id: string;
  name: string;
  active: boolean;
  manager_eligible: boolean;
};

function Confirmation() {
  return (
    <>
      <label>
        Reason
        <input name="reason" required maxLength={500} />
      </label>
      <label className="platform-confirm">
        <input type="checkbox" name="confirmed" required />I confirm this
        administrative change.
      </label>
    </>
  );
}

export function CreatePlatformUser() {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const router = useRouter();
  return (
    <>
      <Link href="/platform/users">Users</Link>
      <h1>Create account</h1>
      <section className="panel">
        <p>
          This creates an organization-free account and sends verification and
          password-setup links. No password is shown or chosen by the
          administrator. Assign membership after verification, or use an
          organization invitation instead.
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
              const user = await api<Account>("/platform/users", {
                method: "POST",
                body: JSON.stringify({
                  email: f.get("email"),
                  first_name: f.get("first_name"),
                  last_name: f.get("last_name"),
                  reason: f.get("reason"),
                  confirmed: f.get("confirmed") === "on",
                }),
              });
              router.push(`/platform/users/${user.id}`);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setPending(false);
            }
          }}
        >
          <label>
            First name
            <input name="first_name" required maxLength={100} />
          </label>
          <label>
            Last name
            <input name="last_name" maxLength={100} />
          </label>
          <label>
            Email
            <input name="email" type="email" required maxLength={254} />
          </label>
          <Confirmation />
          <button className="button primary" disabled={pending}>
            {pending ? "Creating..." : "Create account"}
          </button>
        </form>
      </section>
    </>
  );
}

export function PlatformUser({ id }: { id: string }) {
  const [revision, setRevision] = useState(0);
  const path = `/platform/users/${encodeURIComponent(id)}`;
  const result = useResource<Account>(path, revision);
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [orgSearch, setOrgSearch] = useState("");
  const [employeeSearch, setEmployeeSearch] = useState("");
  const organizations = useResource<{ items: { id: string; name: string }[] }>(
    `/platform/organizations?q=${encodeURIComponent(orgSearch)}`,
  );
  const user = result.data;
  const employees = useResource<{ items: Employee[] }>(
    user?.organization_id
      ? `/platform/organizations/${user.organization_id}/employees?q=${encodeURIComponent(employeeSearch)}`
      : null,
  );
  if (!user)
    return result.error ? <ErrorBox message={result.error} /> : <Loading />;
  const owner = user.role === "OWNER" && !!user.organization_id;
  const choose = (name: string) => {
    setError("");
    setAction(name);
    setEmployeeSearch("");
  };
  return (
    <>
      <Link href="/platform/users">Users</Link>
      <h1>{user.name}</h1>
      <p>
        {user.email} · {user.active ? "Active" : "Disabled"} ·{" "}
        {user.email_verified ? "Verified" : "Unverified"}
      </p>
      {message && <p role="status">{message}</p>}
      <section className="panel">
        <h2>Account and access</h2>
        <dl className="access-summary">
          <div>
            <dt>Platform administration</dt>
            <dd>
              {user.is_platform_admin
                ? "Enabled (separate authority)"
                : "Not granted"}
            </dd>
          </div>
          <div>
            <dt>Organization</dt>
            <dd>
              {user.organization_id ? (
                <Link href={`/platform/organizations/${user.organization_id}`}>
                  {user.organization_name}
                </Link>
              ) : (
                "No customer membership"
              )}
            </dd>
          </div>
          <div>
            <dt>Customer role</dt>
            <dd>{user.organization_id ? user.role : "None"}</dd>
          </div>
          <div>
            <dt>Customer operational access</dt>
            <dd>{user.operational_access ? "Active" : "Inactive"}</dd>
          </div>
          <div>
            <dt>Effective customer permissions</dt>
            <dd>{user.permissions.join(", ") || "None"}</dd>
          </div>
          {[
            ["Created", user.created_at],
            ["Last account update", user.updated_at],
            ["Last session issued", user.last_session_at],
            ["Deactivated", user.deactivated_at],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <dt>{label}</dt>
              <dd>
                {typeof value === "number" ? date(value) : "Not recorded"}
              </dd>
            </div>
          ))}
        </dl>
        <div className="platform-actions">
          <button
            className="button secondary"
            onClick={() => choose("Edit name")}
          >
            Edit name
          </button>
          <button
            className="button secondary"
            disabled={owner || !!user.is_platform_admin || !user.active}
            onClick={() => choose("Change email")}
          >
            Change email
          </button>
          <button
            className="button secondary"
            disabled={!user.active || user.email_verified}
            onClick={() => choose("Resend verification")}
          >
            Resend verification
          </button>
          <button
            className="button secondary"
            disabled={!user.active}
            onClick={() => choose("Send password reset")}
          >
            Send password reset
          </button>
          <button
            className={`button secondary ${user.active ? "platform-danger" : ""}`}
            disabled={user.active && (owner || !!user.is_platform_admin)}
            onClick={() =>
              choose(user.active ? "Deactivate account" : "Reactivate account")
            }
          >
            {user.active ? "Deactivate account" : "Reactivate account"}
          </button>
        </div>
        <p>
          Deactivation keeps all historical records. Existing passwords are
          never available. Owner changes require a confirmed replacement; active
          platform-admin email/deactivation requires the trusted operator
          recovery workflow.
        </p>
      </section>
      <section className="panel">
        <h2>Membership and employee relationship</h2>
        <p>
          {user.employee
            ? `${user.employee.name} · Manager: ${user.employee.manager_name || "Unassigned"}`
            : "No tracked employee linked. Linking never changes account permissions."}
        </p>
        <div className="platform-actions">
          <button
            className="button secondary"
            disabled={owner}
            onClick={() => choose("Change membership")}
          >
            Change membership / role
          </button>
          <button
            className="button secondary platform-danger"
            disabled={owner || !user.organization_id}
            onClick={() => choose("Remove membership")}
          >
            Remove membership
          </button>
          <button
            className="button secondary"
            disabled={!user.organization_id}
            onClick={() => choose("Link employee")}
          >
            Link / unlink employee
          </button>
          <button
            className="button secondary"
            disabled={!user.employee}
            onClick={() => choose("Change manager")}
          >
            Change manager
          </button>
        </div>
        {owner && (
          <p>
            Use the organization page to transfer ownership before changing or
            removing this membership.
          </p>
        )}
      </section>
      <section className="panel">
        <h2>Recent account activity</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Reason / details</th>
              </tr>
            </thead>
            <tbody>
              {user.activity.map((v) => (
                <tr key={v.id}>
                  <td>{date(v.created_at)}</td>
                  <td>{v.action}</td>
                  <td>
                    <Link href={`/platform/users/${v.actor_id}`}>
                      {v.actor_id}
                    </Link>
                  </td>
                  <td>
                    {v.reason}
                    <pre>{JSON.stringify(v.details, null, 2)}</pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!user.activity.length && <p>No recent administrative changes.</p>}
        </div>
      </section>
      {action && (
        <Dialog
          key={action}
          title={action}
          onClose={() => {
            if (!pending) setAction("");
          }}
        >
          {error && <ErrorBox message={error} />}
          <p>
            {action === "Change email"
              ? "The old address is notified. The new address must verify again. Sessions, reset/verification credentials and pending invitations are revoked."
              : action === "Change membership" || action === "Remove membership"
                ? "Existing sessions are revoked. Tracked employee links are removed when leaving an organization; company history stays with its original organization."
                : action === "Send password reset"
                  ? "A secure reset link goes to the account's current email through the configured mail provider. You cannot view the link or choose their password."
                  : action === "Deactivate account"
                    ? "The account loses access and existing sessions are revoked. Calls, QA, employee profiles and audit history remain intact."
                    : "This change is recorded in platform activity."}
          </p>
          <form
            className="account-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setPending(true);
              setError("");
              const f = new FormData(e.currentTarget);
              const body: Record<string, unknown> = {
                revision: user.revision,
                reason: f.get("reason"),
                confirmed: f.get("confirmed") === "on",
              };
              let endpoint = path;
              let method = "PUT";
              if (action === "Edit name") {
                endpoint += "/profile";
                body.first_name = f.get("first_name");
                body.last_name = f.get("last_name");
              } else if (action === "Change email") {
                endpoint += "/email";
                body.email = f.get("email");
              } else if (action.includes("activate account")) {
                endpoint += "/status";
                body.active = action === "Reactivate account";
              } else if (
                action === "Change membership" ||
                action === "Remove membership"
              ) {
                endpoint += "/membership";
                body.organization_id =
                  action === "Remove membership"
                    ? null
                    : f.get("organization_id") || null;
                body.role = f.get("role") || "EMPLOYEE";
              } else if (action === "Link employee") {
                endpoint += "/employee-link";
                body.employee_id = f.get("employee_id") || null;
              } else if (action === "Change manager") {
                endpoint += "/manager";
                body.manager_id = f.get("manager_id") || null;
                body.employee_revision = user.employee?.revision;
              } else {
                endpoint +=
                  action === "Send password reset"
                    ? "/password-reset"
                    : "/verification";
                method = "POST";
              }
              try {
                const r = await api<{ message?: string }>(endpoint, {
                  method,
                  body: JSON.stringify(body),
                });
                setMessage(r.message || `${action} completed.`);
                setAction("");
                setRevision((v) => v + 1);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setPending(false);
              }
            }}
          >
            {action === "Edit name" && (
              <>
                <label>
                  First name
                  <input
                    name="first_name"
                    required
                    maxLength={100}
                    defaultValue={user.first_name ?? user.name}
                  />
                </label>
                <label>
                  Last name
                  <input
                    name="last_name"
                    maxLength={100}
                    defaultValue={user.last_name ?? ""}
                  />
                </label>
              </>
            )}
            {action === "Change email" && (
              <label>
                New email
                <input name="email" type="email" required maxLength={254} />
              </label>
            )}
            {action === "Change membership" && (
              <>
                <label>
                  Find organization
                  <input
                    value={orgSearch}
                    onChange={(e) => setOrgSearch(e.target.value)}
                  />
                </label>
                <label>
                  New organization
                  <select
                    name="organization_id"
                    defaultValue={user.organization_id || ""}
                  >
                    <option value="">No organization</option>
                    {organizations.data?.items.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Customer role
                  <select
                    name="role"
                    defaultValue={owner ? "ADMIN" : user.role}
                  >
                    {[
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
              </>
            )}
            {(action === "Link employee" || action === "Change manager") && (
              <>
                <label>
                  Find employee / manager
                  <input
                    value={employeeSearch}
                    onChange={(e) => setEmployeeSearch(e.target.value)}
                  />
                </label>
                <label>
                  {action === "Link employee" ? "Tracked employee" : "Manager"}
                  <select
                    name={
                      action === "Link employee" ? "employee_id" : "manager_id"
                    }
                    defaultValue=""
                  >
                    <option value="">
                      {action === "Link employee"
                        ? "Unlink employee"
                        : "No manager"}
                    </option>
                    {employees.data?.items
                      .filter(
                        (v) =>
                          action === "Link employee" ||
                          (v.manager_eligible &&
                            v.active &&
                            v.id !== user.employee?.id),
                      )
                      .map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name}
                        </option>
                      ))}
                  </select>
                </label>
              </>
            )}
            <Confirmation />
            <button
              className={`button primary ${action === "Deactivate account" || action === "Remove membership" ? "platform-danger" : ""}`}
              disabled={pending}
            >
              {pending ? "Saving..." : "Confirm"}
            </button>
          </form>
        </Dialog>
      )}
    </>
  );
}

export function OrganizationOwnership({
  id,
  changed,
}: {
  id: string;
  changed: () => void;
}) {
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState("");
  const result = useResource<{ owners: User[]; candidates: User[] }>(
    `/platform/organizations/${id}/ownership?q=${encodeURIComponent(search)}`,
    revision,
  );
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const owner = result.data?.owners.length === 1 ? result.data.owners[0] : null;
  return (
    <section className="panel">
      <h2>Organization Owner</h2>
      {result.error && <ErrorBox message={result.error} />}
      <p>
        {result.data?.owners.map((o) => (
          <Link key={o.id} href={`/platform/users/${o.id}`}>
            {o.name} · {o.email}{" "}
          </Link>
        )) || "Loading Owner..."}
      </p>
      {message && <p role="status">{message}</p>}
      <div className="platform-actions">
        <button
          className="button secondary"
          disabled={!owner}
          onClick={() => {
            setError("");
            setAction("Transfer ownership");
          }}
        >
          Transfer ownership
        </button>
        <button
          className="button secondary"
          onClick={() => {
            setError("");
            setAction("Invite replacement Owner");
          }}
        >
          Invite replacement Owner
        </button>
        <button
          className="button secondary"
          onClick={() => {
            setError("");
            setAction("Edit organization");
          }}
        >
          Edit organization
        </button>
      </div>
      <p>
        A replacement invitation joins as Admin. Ownership changes only through
        a separate confirmed transfer. The current Owner is retained until then.
      </p>
      {action && (
        <Dialog
          key={action}
          title={action}
          onClose={() => {
            if (!pending) setAction("");
          }}
        >
          {error && <ErrorBox message={error} />}
          <p>
            Current Owner: {owner?.name || "None / ambiguous"}. A transfer
            demotes that Owner to Admin, promotes the selected verified member,
            notifies both and revokes their sessions.
          </p>
          <form
            className="account-form"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              setPending(true);
              setError("");
              let endpoint = `/platform/organizations/${id}`;
              let method = "PUT";
              const body: Record<string, unknown> = {
                reason: f.get("reason"),
                confirmed: f.get("confirmed") === "on",
              };
              if (action === "Transfer ownership") {
                endpoint += "/owner";
                body.current_owner_id = owner?.id;
                body.new_owner_id = f.get("new_owner_id");
              } else if (action === "Edit organization") {
                endpoint += "/profile";
                body.name = f.get("name");
              } else {
                endpoint += "/invitations";
                method = "POST";
                body.email = f.get("email");
                body.role = "ADMIN";
                body.purpose = "owner_replacement";
              }
              try {
                await api(endpoint, { method, body: JSON.stringify(body) });
                setAction("");
                setMessage(`${action} completed.`);
                setRevision((v) => v + 1);
                changed();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setPending(false);
              }
            }}
          >
            {action === "Transfer ownership" && (
              <>
                <label>
                  Find replacement
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </label>
                <label>
                  Replacement Owner
                  <select name="new_owner_id" required defaultValue="">
                    <option value="" disabled>
                      Select an active verified member
                    </option>
                    {result.data?.candidates.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} · {c.email}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            {action === "Invite replacement Owner" && (
              <label>
                Candidate email
                <input name="email" type="email" required maxLength={254} />
              </label>
            )}
            {action === "Edit organization" && (
              <label>
                Organization name
                <input name="name" required maxLength={120} />
              </label>
            )}
            <Confirmation />
            <button className="button primary" disabled={pending}>
              {pending ? "Saving..." : "Confirm"}
            </button>
          </form>
        </Dialog>
      )}
    </section>
  );
}
