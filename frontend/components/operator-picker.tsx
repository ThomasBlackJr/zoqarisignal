"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useDrive } from "./shell";
import { ErrorBox } from "./ui";

type Operator = { id: string; name: string };
export function OperatorPicker({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  const { user } = useDrive();
  const allowed = ["OWNER", "ADMIN", "MANAGER"].includes(user.role);
  const [items, setItems] = useState<Operator[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Operator | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!allowed) return;
    let alive = true;
    const timer = setTimeout(() => {
      api<{ items: Operator[] }>(
        "/employees?active=true&q=" + encodeURIComponent(search),
      )
        .then((v) => {
          if (alive) {
            setItems(v.items);
            setError("");
            setLoading(false);
          }
        })
        .catch((e) => {
          if (alive) {
            setError(e.message);
            setLoading(false);
          }
        });
    }, 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [search, allowed]);
  if (!allowed)
    return (
      <p className="muted">
        An Owner, Admin or Manager can assign an operator after upload.
      </p>
    );
  const choices =
    selected && !items.some((e) => e.id === selected.id)
      ? [selected, ...items]
      : items;
  return (
    <fieldset className="operator-picker" disabled={disabled}>
      <legend>
        Operator / Call Owner <small>(optional)</small>
      </legend>
      <label>
        Find operator
        <input
          value={search}
          placeholder="Search by name…"
          onChange={(e) => {
            setSearch(e.target.value);
            setLoading(true);
          }}
        />
      </label>
      <label>
        Assign operator
        <select
          value={value}
          onChange={(e) => {
            setSelected(choices.find((o) => o.id === e.target.value) ?? null);
            onChange(e.target.value);
          }}
        >
          <option value="">Leave unassigned</option>
          {choices.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
      </label>
      <small role="status">
        {loading
          ? "Loading operators…"
          : !items.length
            ? "No matching active operators. You can upload unassigned."
            : "Search to find operators beyond the first 100 results."}
      </small>
      {error && <ErrorBox message={error} />}
    </fieldset>
  );
}
