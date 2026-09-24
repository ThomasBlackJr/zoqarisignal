"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
import { useDrive } from "@/components/shell";
import { Dialog } from "@/components/dialog";
type Rule = {
  id?: string;
  phrase: string;
  enabled: boolean;
  severity: string;
  notify: boolean;
  recipients: string[];
  revision: number;
};
const blank: Rule = {
  phrase: "",
  enabled: true,
  severity: "attention",
  notify: false,
  recipients: [],
  revision: 1,
};
export default function Page() {
  const { user } = useDrive();
  const [data, setData] = useState<{
    items: Rule[];
    recipients: { id: string; name: string; email: string }[];
  }>({ items: [], recipients: [] });
  const [draft, setDraft] = useState<Rule>(blank);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [notifications, setNotifications] = useState<
    { id: string; audit_number: string; status: string }[]
  >([]);
  const [retry, setRetry] = useState<string | null>(null);
  async function load() {
    setData(await api("/flag-rules"));
    setNotifications(await api("/flag-notifications"));
  }
  useEffect(() => {
    Promise.all([
      api<typeof data>("/flag-rules"),
      api<typeof notifications>("/flag-notifications"),
    ])
      .then(([rules, notices]) => {
        setData(rules);
        setNotifications(notices);
      })
      .catch((e) => setError(e.message));
  }, []);
  if (!["OWNER", "ADMIN"].includes(user.role))
    return (
      <p className="notice">Only Owners and Admins configure flagged terms.</p>
    );
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { id, ...body } = draft;
      await api(id ? `/flag-rules/${id}` : "/flag-rules", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(body),
      });
      setDraft(blank);
      await load();
      setMessage(
        "Rule saved. New processing uses this rule; scan existing transcripts to apply it to your library.",
      );
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
          <div className="eyebrow">ORGANIZATION ALERTS</div>
          <h1>Flagged terms</h1>
          <p>
            Deterministic transcript matches. Notification recipients must be
            verified members of your organization.
          </p>
        </div>
      </div>
      {error && <ErrorBox message={error} />}{" "}
      {message && <p role="status">{message}</p>}
      <section className="panel">
        <form className="dialog-content account-form" onSubmit={save}>
          <h2>{draft.id ? "Edit rule" : "Add rule"}</h2>
          <label>
            Term or phrase
            <input
              required
              maxLength={200}
              value={draft.phrase}
              onChange={(e) => setDraft({ ...draft, phrase: e.target.value })}
            />
          </label>
          <label>
            Severity
            <select
              value={draft.severity}
              onChange={(e) => setDraft({ ...draft, severity: e.target.value })}
            >
              <option value="info">Information</option>
              <option value="attention">Attention</option>
              <option value="urgent">Urgent</option>
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) =>
                setDraft({ ...draft, enabled: e.target.checked })
              }
            />{" "}
            Enabled
          </label>
          <label>
            <input
              type="checkbox"
              checked={draft.notify}
              onChange={(e) => setDraft({ ...draft, notify: e.target.checked })}
            />{" "}
            Email notification
          </label>
          {draft.notify && (
            <fieldset>
              <legend>Recipients</legend>
              {data.recipients.map((u) => (
                <label key={u.id}>
                  <input
                    type="checkbox"
                    checked={draft.recipients.includes(u.id)}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        recipients: e.target.checked
                          ? [...draft.recipients, u.id]
                          : draft.recipients.filter((x) => x !== u.id),
                      })
                    }
                  />
                  {u.name} · {u.email}
                </label>
              ))}
            </fieldset>
          )}
          <p className="notice">
            Configured alerts send the audit reference, phrase and secure review
            link. Transcript text is not included. Local development writes an
            outbox message instead of sending.
          </p>
          <div className="form-actions">
            <button className="button primary" disabled={busy}>
              Save rule
            </button>
            {draft.id && (
              <button
                type="button"
                className="button secondary"
                onClick={() => setDraft(blank)}
              >
                Cancel editing
              </button>
            )}
          </div>
        </form>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Configured rules</h2>
          <button
            className="button secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                let offset: number | null = 0;
                let total = 0;
                while (offset !== null) {
                  const v: { scanned: number; next_offset: number | null } =
                    await api(`/flag-rules/scan-existing?offset=${offset}`, {
                      method: "POST",
                    });
                  total += v.scanned;
                  offset = v.next_offset;
                }
                setMessage(
                  `Scanned ${total} interactions. Configured new alerts are queued.`,
                );
                await load();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Scan existing transcripts
          </button>
        </div>
        <div className="dialog-content">
          {data.items.length ? (
            data.items.map((r) => (
              <div className="module-option" key={r.id}>
                <span>
                  {r.phrase} · {r.enabled ? "Enabled" : "Disabled"} ·{" "}
                  {r.notify ? "Email alerts" : "No email alerts"}
                </span>
                <button
                  className="button secondary"
                  onClick={() => setDraft(r)}
                >
                  Edit {r.phrase}
                </button>
              </div>
            ))
          ) : (
            <p>No rules configured.</p>
          )}
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Notification activity</h2>
          <button
            className="button secondary"
            onClick={() => void load().catch((e) => setError(e.message))}
          >
            Refresh activity
          </button>
        </div>
        <div className="dialog-content">
          <p>
            Submitted means accepted by SMTP, not confirmed delivered. Uncertain
            attempts are never automatically retried.
          </p>
          {notifications.map((n) => (
            <div className="module-option" key={n.id}>
              <span>
                {n.audit_number} · {n.status}
              </span>
              {["uncertain", "blocked"].includes(n.status) && (
                <button
                  className="button secondary"
                  onClick={() => setRetry(n.id)}
                >
                  Review retry
                </button>
              )}
            </div>
          ))}
        </div>
      </section>
      {retry && (
        <Dialog title="Retry notification" onClose={() => setRetry(null)}>
          <p>
            The previous attempt may already have been accepted by the mail
            server. Retrying could send a duplicate.
          </p>
          <button
            className="button primary"
            onClick={async () => {
              try {
                await api(`/flag-notifications/${retry}/retry`, {
                  method: "POST",
                });
                setRetry(null);
                await load();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Queue retry
          </button>
        </Dialog>
      )}
    </>
  );
}
