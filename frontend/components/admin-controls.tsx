"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useDrive } from "./shell";
import { Dialog } from "./dialog";
import { ErrorBox } from "./ui";

export function AdminControls({
  kind,
  id,
  revision,
  active,
  processing = false,
  onSaved,
}: {
  kind: "employee" | "call";
  id: string;
  revision?: number;
  active?: boolean;
  processing?: boolean;
  onSaved?: () => Promise<void>;
}) {
  const { user } = useDrive();
  const router = useRouter();
  const [action, setAction] = useState<"archive" | "delete" | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  if (!["OWNER", "ADMIN"].includes(user.role)) return null;
  const noun = kind === "call" ? "interaction" : "employee";
  async function submit() {
    setSaving(true);
    setError("");
    try {
      const result = await api<{ status: string }>(
        `/${kind === "call" ? "calls" : "employees"}/${id}${action === "archive" ? "/archive" : ""}`,
        {
          method: action === "archive" ? "POST" : "DELETE",
          ...(kind === "employee"
            ? { body: JSON.stringify({ revision }) }
            : {}),
        },
      );
      if (action === "archive") {
        await onSaved?.();
        setAction(null);
      } else
        router.push(
          kind === "call"
            ? `/calls${result.status === "audio_deletion_pending" ? "?cleanup=pending" : ""}`
            : "/employees",
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="panel admin-controls">
      <h2>Administrative controls</h2>
      <p>
        {kind === "employee"
          ? "Archive to retain history and prevent new assignments. Permanent deletion is only available when no business history or relationships depend on this person."
          : "Deletion permanently removes the recording, transcript, evaluations and related interaction history. It cannot be undone."}
      </p>
      {processing && (
        <p>Wait for active processing to finish before deletion.</p>
      )}
      <div className="form-actions">
        {kind === "employee" && active && (
          <button
            className="button secondary"
            onClick={() => {
              setAction("archive");
              setError("");
            }}
          >
            Archive employee
          </button>
        )}
        <button
          className="button danger"
          disabled={processing}
          onClick={() => {
            setAction("delete");
            setConfirmation("");
            setError("");
          }}
        >
          {kind === "call"
            ? "Delete interaction"
            : "Permanently delete employee"}
        </button>
      </div>
      {action && (
        <Dialog
          title={`${action === "archive" ? "Archive" : "Permanently delete"} this ${noun}?`}
          onClose={() => !saving && setAction(null)}
        >
          <p>
            {action === "archive"
              ? "Reporting relationships and historical performance remain intact. New assignments are blocked. Restore through Active employee in employee details."
              : kind === "call"
                ? "This permanently removes the recording and associated Signal data, including its transcript and all QA evaluations. Batch history will show Deleted interaction. This cannot be undone."
                : "Only unused employees can be permanently deleted. Historical references block deletion; archive instead to retain attribution."}
          </p>
          {action === "delete" && (
            <label>
              Type DELETE to confirm
              <input
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                autoComplete="off"
              />
            </label>
          )}
          {error && <ErrorBox message={error} />}
          <div className="form-actions">
            <button
              className="button secondary"
              disabled={saving}
              onClick={() => setAction(null)}
            >
              Cancel
            </button>
            <button
              className={`button ${action === "delete" ? "danger" : "primary"}`}
              disabled={
                saving || (action === "delete" && confirmation !== "DELETE")
              }
              onClick={submit}
            >
              {saving
                ? "Saving…"
                : action === "archive"
                  ? "Confirm archive"
                  : "Confirm permanent deletion"}
            </button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
