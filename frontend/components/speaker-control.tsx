"use client";
import { useState } from "react";
import { api, Conversation, ConversationTurn, date } from "@/lib/api";
import { Dialog } from "./dialog";
import { ErrorBox } from "./ui";

export function SpeakerControl({
  turn,
  conversation,
  callId,
  onSaved,
}: {
  turn: ConversationTurn;
  conversation: Conversation;
  callId: string;
  onSaved: () => Promise<void>;
}) {
  const effective = turn.effective_role ?? turn.speaker_role;
  const [role, setRole] = useState<string | null>(null);
  const [scope, setScope] = useState("turn");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const count = conversation.turns.filter(
    (t) => t.speaker_id === turn.speaker_id,
  ).length;
  async function save() {
    setSaving(true);
    setError("");
    try {
      await api(`/calls/${callId}/speakers`, {
        method: "POST",
        body: JSON.stringify({
          source_fingerprint: conversation.source_fingerprint,
          source_start: turn.source_start,
          source_end: turn.source_end,
          role: role === "RESET" ? null : role,
          scope,
          revision: conversation.revision ?? 0,
        }),
      });
      await onSaved();
      setRole(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <select
        className={`speaker-role ${effective.toLowerCase()}`}
        aria-label={`Speaker role for turn at ${turn.source_start}`}
        value={effective}
        onChange={(e) => {
          setScope("turn");
          setError("");
          setRole(e.target.value);
        }}
      >
        {["DISPATCHER", "CALLER", "UNKNOWN"].map((r) => (
          <option key={r}>{r}</option>
        ))}
      </select>
      {turn.manual_role && (
        <span className="manual-label">
          Corrected by {turn.corrector_name} ·{" "}
          {turn.corrected_at ? date(turn.corrected_at) : ""}
          <button
            className="text-link"
            onClick={() => {
              setRole("RESET");
              setScope("turn");
            }}
          >
            Reset role
          </button>
        </span>
      )}
      {role && (
        <Dialog
          title={
            role === "RESET" ? "Restore inferred role" : "Correct speaker role"
          }
          onClose={() => !saving && setRole(null)}
        >
          <p>
            Original inference:{" "}
            <strong>{turn.inferred_role ?? turn.speaker_role}</strong>. This
            changes the displayed role only. Transcript wording and existing QA
            remain intact.
          </p>
          <label>
            Apply correction to
            <select value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="turn">This conversational turn only</option>
              {turn.speaker_id !== null && (
                <option value="speaker">
                  All {count} turns with Speaker ID {turn.speaker_id}
                </option>
              )}
            </select>
          </label>
          <p className="notice">
            {scope === "speaker"
              ? `${count} turns with Speaker ID ${turn.speaker_id}`
              : "1 conversational turn"}{" "}
            → {role === "RESET" ? "original inferred role" : role}
          </p>
          {error && <ErrorBox message={error} />}
          <div className="form-actions">
            <button
              className="button secondary"
              onClick={() => setRole(null)}
              disabled={saving}
            >
              Cancel
            </button>
            <button className="button primary" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Apply correction"}
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
