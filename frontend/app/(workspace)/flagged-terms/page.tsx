"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox, Loading } from "@/components/ui";
import { useDrive } from "@/components/shell";
import { Dialog } from "@/components/dialog";
import { Bell, Flag, Pencil, Trash2 } from "lucide-react";
import "@/app/flagged-terms.css";
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
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<Rule | null>(null);
  const [confirmScan, setConfirmScan] = useState(false);
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
        setLoading(false);
        setData(rules);
        setNotifications(notices);
      })
      .catch((e) => {
        setLoading(false);
        setError(e.message);
      });
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
            Catch important words and phrases in your organization’s
            transcripts.
          </p>
        </div>
      </div>
      {error && <ErrorBox message={error} />}{" "}
      {message && <p role="status">{message}</p>}
      <div className="flag-workspace">
        <section className="panel flag-editor">
          <form className="dialog-content account-form" onSubmit={save}>
            <h2>{draft.id ? "Edit rule" : "Add Flag"}</h2>
            <p className="muted">
              Choose what to match and how your team is notified.
            </p>
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
                onChange={(e) =>
                  setDraft({ ...draft, severity: e.target.value })
                }
              >
                <option value="info">Information</option>
                <option value="attention">Attention</option>
                <option value="urgent">Urgent</option>
              </select>
            </label>
            <div className="flag-settings">
              <div className="flag-setting">
                <div>
                  <strong>Rule status</strong>
                  <small>
                    {draft.enabled
                      ? "Active for new processing"
                      : "Inactive · matching paused"}
                  </small>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-label="Enabled"
                  aria-checked={draft.enabled}
                  className="flag-switch"
                  onClick={() =>
                    setDraft({ ...draft, enabled: !draft.enabled })
                  }
                >
                  <span />
                </button>
              </div>
              <div className="flag-setting">
                <div>
                  <strong>Email notification</strong>
                  <small>
                    {draft.notify
                      ? "Notify selected recipients"
                      : "Record matches without email"}
                  </small>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-label="Email notification"
                  aria-checked={draft.notify}
                  className="flag-switch"
                  onClick={() => setDraft({ ...draft, notify: !draft.notify })}
                >
                  <span />
                </button>
              </div>
            </div>
            {draft.notify && (
              <fieldset className="flag-recipients">
                <legend>Verified recipients</legend>
                {!data.recipients.length && (
                  <p className="muted">
                    No verified organization members are available.
                  </p>
                )}
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
                    <span>
                      <strong>{u.name}</strong>
                      <small>{u.email}</small>
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
            <p className="notice">
              Configured alerts send the audit reference, phrase and secure
              review link. Transcript text is not included.
            </p>
            <div className="form-actions">
              <button className="button primary" disabled={busy}>
                {busy ? "Saving…" : draft.id ? "Save changes" : "Add Flag"}
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
        <section className="panel flag-library">
          <div className="panel-heading">
            <div>
              <h2>Configured rules</h2>
              <p>
                {data.items.filter((r) => r.enabled).length} active ·{" "}
                {data.items.length} total
              </p>
            </div>
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setConfirmScan(true)}
            >
              Scan existing transcripts
            </button>
          </div>
          {confirmScan && (
            <Dialog
              title="Scan existing transcripts?"
              onClose={() => !busy && setConfirmScan(false)}
            >
              <p>
                This scans saved transcripts using current rules, without
                transcription or QA requests. New matches may send configured
                email alerts. Historical evidence remains intact.
              </p>
              <div className="form-actions">
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => setConfirmScan(false)}
                >
                  Cancel
                </button>
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    try {
                      let offset: number | null = 0;
                      let total = 0;
                      while (offset !== null) {
                        const v: {
                          scanned: number;
                          next_offset: number | null;
                        } = await api(
                          `/flag-rules/scan-existing?offset=${offset}`,
                          {
                            method: "POST",
                          },
                        );
                        total += v.scanned;
                        offset = v.next_offset;
                      }
                      setMessage(
                        `Scanned ${total} interactions. Configured new alerts are queued.`,
                      );
                      await load();
                      setConfirmScan(false);
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {busy ? "Scanning…" : "Confirm scan"}
                </button>
              </div>
            </Dialog>
          )}
          <div className="flag-rule-list">
            {loading ? (
              <Loading />
            ) : data.items.length ? (
              data.items.map((r) => (
                <article className="flag-rule" key={r.id}>
                  <div className="flag-rule-heading">
                    <span className="flag-rule-icon">
                      <Flag size={18} aria-hidden="true" />
                    </span>
                    <h3>{r.phrase}</h3>
                    <span
                      className={`flag-status ${r.enabled ? "active" : "inactive"}`}
                    >
                      {r.enabled ? "Active" : "Inactive"}
                    </span>
                  </div>
                  <div className="flag-rule-meta">
                    <span className={`flag-severity ${r.severity}`}>
                      {r.severity === "info"
                        ? "Information"
                        : r.severity === "urgent"
                          ? "Urgent"
                          : "Attention"}
                    </span>
                    <span>
                      <Bell size={14} aria-hidden="true" />
                      {r.notify
                        ? `Email alerts · ${r.recipients.length} ${r.recipients.length === 1 ? "recipient" : "recipients"}`
                        : "No email alerts"}
                    </span>
                  </div>
                  <div className="form-actions">
                    <button
                      className="button secondary"
                      aria-label={`Edit ${r.phrase}`}
                      disabled={busy}
                      onClick={() => {
                        setDraft(r);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                    >
                      <Pencil size={14} aria-hidden="true" /> Edit
                    </button>
                    <button
                      className="button danger"
                      aria-label={`Delete ${r.phrase}`}
                      disabled={busy}
                      onClick={() => setDeleting(r)}
                    >
                      <Trash2 size={14} aria-hidden="true" /> Delete
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <div className="flag-empty">
                <Flag size={24} aria-hidden="true" />
                <h3>No rules yet</h3>
                <p>Add a term or phrase to start flagging important moments.</p>
              </div>
            )}
          </div>
        </section>
      </div>
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
          {!notifications.length && (
            <p className="muted">No notification activity yet.</p>
          )}
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
      {deleting && (
        <Dialog
          title="Delete flag rule?"
          onClose={() => !busy && setDeleting(null)}
        >
          <p>
            Delete “{deleting.phrase}” from future matching? Existing flags and
            audit evidence will remain available in detection history.
          </p>
          {error && <ErrorBox message={error} />}
          <div className="form-actions">
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setDeleting(null)}
            >
              Cancel
            </button>
            <button
              className="button danger"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await api(`/flag-rules/${deleting.id}`, {
                    method: "DELETE",
                    body: JSON.stringify({ revision: deleting.revision }),
                  });
                  if (draft.id === deleting.id) setDraft(blank);
                  setDeleting(null);
                  await load();
                  setMessage("Rule deleted. Historical evidence is preserved.");
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? "Deleting…" : "Delete rule"}
            </button>
          </div>
        </Dialog>
      )}
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
