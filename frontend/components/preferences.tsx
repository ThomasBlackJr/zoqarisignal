"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { ErrorBox } from "./ui";

export type Preferences = {
  appearance: "light" | "dark" | "system";
  modules: string[];
  revision: number;
};
export const moduleLabels: Record<string, string> = {
  metrics: "Business Overview",
  attention: "Needs Attention",
  issues: "Frequent Quality Issues",
  teams: "Team Performance",
  coaching: "Coaching Opportunities",
  recommendations: "Signal Recommendations",
  processing: "Processing Status",
  recent: "Recent interactions",
  review: "Review queue shortcut",
};
export const defaultModules = [
  "metrics",
  "attention",
  "issues",
  "teams",
  "coaching",
  "recommendations",
  "recent",
];
const Context = createContext<{
  value: Preferences | null;
  save: (v: Preferences) => Promise<void>;
} | null>(null);
export function usePreferences() {
  const v = useContext(Context);
  if (!v) throw new Error("Missing preferences");
  return v;
}
export function PreferenceProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [value, setValue] = useState<Preferences | null>(null);
  const path = usePathname();
  useEffect(() => {
    let active = true;
    // Account pages also support appearance. Anonymous requests must not trigger login redirects.
    fetch("/api/preferences", { credentials: "include", cache: "no-store" })
      .then(async (r) => {
        if (r.status === 401) {
          if (active) setValue(null);
          return;
        }
        if (!r.ok) return;
        const v = await r.json();
        if (active) setValue(v);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [path]);
  const appearance = value?.appearance ?? "system";
  useEffect(() => {
    const system = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        appearance === "system"
          ? system.matches
            ? "dark"
            : "light"
          : appearance;
    };
    apply();
    system.addEventListener("change", apply);
    return () => system.removeEventListener("change", apply);
  }, [appearance]);
  const save = useCallback(async (next: Preferences) => {
    setValue(
      await api<Preferences>("/preferences", {
        method: "PUT",
        body: JSON.stringify(next),
      }),
    );
  }, []);
  return (
    <Context.Provider value={{ value, save }}>{children}</Context.Provider>
  );
}

export function Appearance() {
  const { value, save } = usePreferences();
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  if (!value) return null;
  return (
    <div className="appearance-control">
      <label>
        Appearance
        <select
          aria-label="Appearance"
          value={value.appearance}
          disabled={saving}
          onChange={async (e) => {
            setSaving(true);
            setError("");
            try {
              await save({
                ...value,
                appearance: e.target.value as Preferences["appearance"],
              });
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setSaving(false);
            }
          }}
        >
          <option value="light">Light</option>
          <option value="dark">Dark</option>
          <option value="system">System</option>
        </select>
      </label>
      {error && <ErrorBox message={error} />}
    </div>
  );
}

export function DashboardEditor() {
  const { value, save } = usePreferences();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  if (!value) return null;
  return (
    <div className="dashboard-editor">
      <button
        className="button secondary"
        onClick={() => {
          setDraft([...value.modules]);
          setOpen(!open);
          setError("");
        }}
      >
        Customize dashboard
      </button>
      {open && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Edit dashboard</h2>
              <p>Visibility and order apply only to your account.</p>
            </div>
          </div>
          <div className="dashboard-options">
            {[
              ...draft,
              ...Object.keys(moduleLabels).filter((k) => !draft.includes(k)),
            ].map((k) => (
              <div className="module-option" key={k}>
                <label>
                  <input
                    type="checkbox"
                    checked={draft.includes(k)}
                    onChange={(e) =>
                      setDraft(
                        e.target.checked
                          ? [...draft, k]
                          : draft.filter((x) => x !== k),
                      )
                    }
                  />
                  {moduleLabels[k]}
                </label>
                {draft.includes(k) && (
                  <div>
                    <button
                      className="button secondary"
                      aria-label={`Move ${moduleLabels[k]} up`}
                      disabled={draft.indexOf(k) === 0}
                      onClick={() => {
                        const a = [...draft],
                          i = a.indexOf(k);
                        [a[i - 1], a[i]] = [a[i], a[i - 1]];
                        setDraft(a);
                      }}
                    >
                      ↑
                    </button>
                    <button
                      className="button secondary"
                      aria-label={`Move ${moduleLabels[k]} down`}
                      disabled={draft.indexOf(k) === draft.length - 1}
                      onClick={() => {
                        const a = [...draft],
                          i = a.indexOf(k);
                        [a[i + 1], a[i]] = [a[i], a[i + 1]];
                        setDraft(a);
                      }}
                    >
                      ↓
                    </button>
                  </div>
                )}
              </div>
            ))}
            {error && <ErrorBox message={error} />}
            <div className="form-actions">
              <button
                className="button secondary"
                disabled={saving}
                onClick={() => setOpen(false)}
              >
                Cancel
              </button>
              <button
                className="button secondary"
                disabled={saving}
                onClick={() => setDraft([...defaultModules])}
              >
                Restore defaults
              </button>
              <button
                className="button primary"
                disabled={saving}
                onClick={async () => {
                  setSaving(true);
                  try {
                    await save({ ...value, modules: draft });
                    setOpen(false);
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setSaving(false);
                  }
                }}
              >
                {saving ? "Saving…" : "Save dashboard"}
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
