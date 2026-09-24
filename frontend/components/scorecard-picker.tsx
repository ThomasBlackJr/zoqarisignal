"use client";
import { useEffect, useState } from "react";
import { api, Rubric } from "@/lib/api";
import { ErrorBox } from "./ui";

export function ScorecardPicker({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  const [items, setItems] = useState<Rubric[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    api<Rubric[]>("/rubrics")
      .then((all) => {
        if (alive) setItems(all.filter((r) => r.status === "ACTIVE"));
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);
  return (
    <div className="scorecard-picker">
      <label>
        Scorecard
        <select
          aria-label="Scorecard"
          value={value}
          disabled={disabled}
          required
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Choose a published scorecard</option>
          {items.map((r) => (
            <option value={r.id} key={r.id}>
              {r.name} · Version {r.version}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">
        Choose the grading standard before processing. Published versions are
        fixed; previous results remain in history.
      </p>
      {error && <ErrorBox message={error} />}
      {!items.length && !error && (
        <p>
          Loading available scorecards. If none appear, an Owner/Admin must
          publish one in Scorecards.
        </p>
      )}
    </div>
  );
}
