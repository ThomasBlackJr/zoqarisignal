"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useDrive } from "./shell";
import { ErrorBox } from "./ui";
type Vocabulary = {
  registered_name: string;
  preferred_name: string | null;
  alternate_names: string[];
  abbreviations: string[];
  pronunciations: string[];
  industry_terms: string[];
};
const lists = [
  "alternate_names",
  "abbreviations",
  "pronunciations",
  "industry_terms",
] as const;
export function TranscriptionVocabulary() {
  const { user } = useDrive();
  const allowed = ["OWNER", "ADMIN"].includes(user.role);
  const [data, setData] = useState<Vocabulary | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!allowed) return;
    let alive = true;
    api<Vocabulary>("/organization/transcription-vocabulary")
      .then((v) => {
        if (alive) setData(v);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [allowed]);
  async function save(form: HTMLFormElement) {
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const fields = new FormData(form);
      const body = {
        preferred_name:
          String(fields.get("preferred_name") ?? "").trim() || null,
        ...Object.fromEntries(
          lists.map((k) => [
            k,
            String(fields.get(k) ?? "")
              .split("\n")
              .map((v) => v.trim())
              .filter(Boolean),
          ]),
        ),
      };
      setData(
        await api<Vocabulary>("/organization/transcription-vocabulary", {
          method: "PUT",
          body: JSON.stringify(body),
        }),
      );
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!allowed) return null;
  return (
    <details className="panel intelligence-panel">
      <summary>Company transcription vocabulary (optional)</summary>
      {error && <ErrorBox message={error} />}
      {data && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save(e.currentTarget);
          }}
        >
          <p>
            Registered company: <strong>{data.registered_name}</strong>. Used
            automatically. Optional vocabulary applies to future transcriptions.
          </p>
          <label>
            Preferred company name
            <input
              name="preferred_name"
              defaultValue={data.preferred_name ?? ""}
              maxLength={120}
            />
          </label>
          {lists.map((k) => (
            <label key={k}>
              {k.replaceAll("_", " ")} (one per line)
              <textarea name={k} defaultValue={data[k].join("\n")} rows={3} />
            </label>
          ))}
          <button className="button secondary" disabled={busy}>
            Save vocabulary
          </button>
          {saved && <p role="status">Vocabulary saved.</p>}
        </form>
      )}
    </details>
  );
}
