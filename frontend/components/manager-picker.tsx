"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox } from "./ui";
type Person = { id: string; name: string; active: boolean };
export function ManagerPicker({
  initial = "",
  exclude,
  filter = false,
  value,
  onChange,
}: {
  initial?: string;
  exclude?: string;
  filter?: boolean;
  value?: string;
  onChange?: (id: string) => void;
}) {
  const [choice, setChoice] = useState(initial);
  const selected = value ?? choice;
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Person[]>([]);
  const [current, setCurrent] = useState<Person | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      api<{ items: Person[] }>(
        `/employees?q=${encodeURIComponent(q)}&${filter ? "managers_only=true" : "managers_only=true&active=true"}`,
      )
        .then((v) => {
          if (alive) setItems(v.items);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    }, 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [q, filter]);
  useEffect(() => {
    let alive = true;
    if (selected && selected !== "unassigned")
      api<Person>(`/employees/${selected}`)
        .then((v) => {
          if (alive) setCurrent(v);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    return () => {
      alive = false;
    };
  }, [selected]);
  return (
    <div className="manager-picker">
      <label>
        Find manager
        <input
          aria-label={filter ? "Find manager filter" : "Find reporting manager"}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search designated managers…"
        />
      </label>
      <label>
        {filter ? "Manager filter" : "Manager"}
        <select
          name="manager_id"
          aria-label={filter ? "Filter by manager" : "Manager"}
          value={selected}
          onChange={(e) => {
            setChoice(e.target.value);
            onChange?.(e.target.value);
          }}
        >
          <option value="">{filter ? "All managers" : "No manager"}</option>
          {filter && (
            <option value="unassigned">
              No manager / unassigned interaction
            </option>
          )}
          {selected &&
            selected !== "unassigned" &&
            !items.some((e) => e.id === selected) && (
              <option value={selected}>
                {current?.id === selected
                  ? current.name + (current.active ? "" : " (inactive)")
                  : "Selected manager"}
              </option>
            )}
          {items
            .filter((e) => e.id !== exclude)
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
                {e.active ? "" : " (inactive)"}
              </option>
            ))}
        </select>
      </label>
      {error && <ErrorBox message={error} />}
    </div>
  );
}
