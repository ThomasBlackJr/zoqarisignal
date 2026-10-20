"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, date } from "@/lib/api";
import { ErrorBox } from "./ui";

type Attribute = {
  key: string;
  label: string;
  value: string | null;
  verified: boolean;
  revision: number;
  origin: string;
  source_start?: number | null;
  source_end?: number | null;
  timestamp?: number | null;
  confidence?: number | null;
};
type Result = {
  id: string;
  filename: string;
  created_at: number;
  employee_name: string | null;
  customer: string | null;
  qa_score: number | null;
  matches: { key: string; label: string; value: string }[];
};
type Results = { items: Result[]; total: number };
function ResultList({
  data,
  onExclude,
}: {
  data: Results;
  onExclude?: (id: string) => void;
}) {
  return (
    <>
      <p>
        {data.total} matching interaction{data.total === 1 ? "" : "s"}
      </p>
      {data.items.map((item) => (
        <article className="intelligence-result" key={item.id}>
          <Link href={`/calls/${item.id}`}>{item.filename}</Link>
          <p>
            {date(item.created_at)} · {item.employee_name ?? "Unassigned"} ·{" "}
            {item.customer ?? "Customer not found"} · QA{" "}
            {item.qa_score ?? "Unavailable"}
          </p>
          <p>{item.matches.map((m) => `${m.label}: ${m.value}`).join(" · ")}</p>
          {onExclude && (
            <button
              className="button secondary"
              onClick={() => onExclude(item.id)}
            >
              Remove relationship
            </button>
          )}
        </article>
      ))}
    </>
  );
}
function AttributeEditor({
  attribute,
  onSave,
}: {
  attribute: Attribute;
  onSave: (value: string | null) => Promise<void>;
}) {
  const [value, setValue] = useState(attribute.value ?? "");
  const [busy, setBusy] = useState(false);
  async function save(next: string | null) {
    setBusy(true);
    try {
      await onSave(next);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="intelligence-attribute">
      <label>
        {attribute.label}
        <input
          aria-label={`${attribute.label} value`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          maxLength={500}
        />
      </label>
      <p>
        {attribute.value ?? "Not found"} ·{" "}
        {attribute.verified
          ? "Verified"
          : attribute.origin === "manual"
            ? "Manual"
            : "Automatic, unverified"}
      </p>
      {attribute.source_start != null && (
        <small>
          Source characters {attribute.source_start}–{attribute.source_end}
          {attribute.timestamp != null
            ? ` · ${attribute.timestamp.toFixed(1)} seconds`
            : ""}
        </small>
      )}
      <div className="intelligence-actions">
        <button
          className="button secondary"
          disabled={busy || !value.trim()}
          onClick={() => void save(value)}
        >
          Save &amp; verify {attribute.label}
        </button>
        <button
          className="button secondary"
          disabled={busy || !attribute.value}
          onClick={() => void save(null)}
        >
          Remove {attribute.label}
        </button>
      </div>
    </div>
  );
}
type Event = {
  id: number;
  key: string;
  actor_id: string | null;
  created_at: number;
  previous: { value: string | null } | null;
  current: { value: string | null };
};
export function CallIntelligence({
  callId,
  onSeek,
}: {
  callId: string;
  onSeek: (seconds: number) => void;
}) {
  const [data, setData] = useState<{
    attributes: Attribute[];
    processed: boolean;
  } | null>(null);
  const [related, setRelated] = useState<Results | null>(null);
  const [offset, setOffset] = useState(0);
  const [history, setHistory] = useState<{
    items: Event[];
    total: number;
  } | null>(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const [attributes, relations, events] = await Promise.all([
      api<{ attributes: Attribute[]; processed: boolean }>(
        `/calls/${callId}/intelligence`,
      ),
      api<Results>(`/calls/${callId}/related?offset=${offset}`),
      api<{ items: Event[]; total: number }>(
        `/calls/${callId}/attributes/history?offset=${historyOffset}`,
      ),
    ]);
    setData(attributes);
    setRelated(relations);
    setHistory(events);
  }, [callId, offset, historyOffset]);
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      if (alive) void load().catch((e) => setError(e.message));
    }, 0);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [load]);
  async function act(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="panel intelligence-panel">
      <div className="panel-heading">
        <div>
          <h2>Call intelligence</h2>
          <p>
            Extracted from the saved transcript. Review identifiers before
            linking calls.
          </p>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <div className="intelligence-grid">
            {data.attributes.map((a) => (
              <div key={a.key}>
                <AttributeEditor
                  key={`${a.key}-${a.revision}`}
                  attribute={a}
                  onSave={(value) =>
                    act(() =>
                      api(`/calls/${callId}/attributes/${a.key}`, {
                        method: "PUT",
                        body: JSON.stringify({
                          value,
                          verified: true,
                          revision: a.revision,
                        }),
                      }),
                    )
                  }
                />
                {a.timestamp != null && (
                  <button
                    className="timestamp"
                    onClick={() => onSeek(a.timestamp!)}
                  >
                    Play {a.label} evidence
                  </button>
                )}
              </div>
            ))}
          </div>
          <p>
            Confidence unavailable: extraction uses conservative rules and
            leaves ambiguous values empty.
          </p>
          <button
            className="button secondary"
            onClick={() =>
              void act(() =>
                api(`/calls/${callId}/intelligence/refresh`, {
                  method: "POST",
                }),
              )
            }
          >
            {data.processed
              ? "Recheck saved transcript"
              : "Extract saved transcript"}
          </button>
          <small>
            {" "}
            Uses the saved transcript; manual values and removals are preserved.
          </small>
        </>
      )}
      {history && (
        <details className="audit-history">
          <summary>Attribute history ({history.total})</summary>
          {history.items.map((e) => (
            <p key={e.id}>
              {date(e.created_at)} ·{" "}
              {e.actor_id ? "Reviewer" : "Automatic extraction"} · {e.key}:{" "}
              {e.previous?.value ?? "Not found"} →{" "}
              {e.current.value ?? "Removed / not found"}
            </p>
          ))}
          <button
            disabled={historyOffset === 0}
            onClick={() => setHistoryOffset((v) => Math.max(0, v - 25))}
          >
            Previous history
          </button>
          <button
            disabled={historyOffset + 25 >= history.total}
            onClick={() => setHistoryOffset((v) => v + 25)}
          >
            Next history
          </button>
        </details>
      )}
      <h3>Related interactions</h3>
      <p>
        Only shared, verified Order # or HAWB identifiers create relationships.
      </p>
      {related && (
        <>
          <ResultList
            data={related}
            onExclude={(id) =>
              void act(() =>
                api(`/calls/${callId}/related/${id}/exclude`, {
                  method: "POST",
                }),
              )
            }
          />
          <button
            disabled={offset === 0}
            onClick={() => setOffset((v) => Math.max(0, v - 20))}
          >
            Previous related
          </button>
          <button
            disabled={offset + 20 >= related.total}
            onClick={() => setOffset((v) => v + 20)}
          >
            Next related
          </button>
        </>
      )}
    </section>
  );
}
export function IntelligenceSearch() {
  const [q, setQ] = useState("");
  const [key, setKey] = useState("");
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<Results | null>(null);
  const [error, setError] = useState("");
  async function search(nextOffset = 0) {
    setError("");
    try {
      const result = await api<Results>(
        `/intelligence/search?${new URLSearchParams({ q, key, offset: String(nextOffset) })}`,
      );
      setResult(result);
      setOffset(nextOffset);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="panel intelligence-panel">
      <h2>Search call intelligence</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
        className="intelligence-actions"
      >
        <label>
          Attribute
          <select
            aria-label="Search attribute"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          >
            <option value="">All attributes</option>
            <option value="customer">Customer</option>
            <option value="address">Address</option>
            <option value="order">Order #</option>
            <option value="hawb">HAWB</option>
          </select>
        </label>
        <label>
          Value
          <input
            aria-label="Search attribute value"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            maxLength={200}
          />
        </label>
        <button className="button" disabled={!q.trim()}>
          Search attributes
        </button>
      </form>
      <p>
        Exact identifiers, ignoring spaces and hyphens. Partial customer names
        and addresses.
      </p>
      {error && <ErrorBox message={error} />}
      {result && (
        <>
          <ResultList data={result} />
          <button
            disabled={offset === 0}
            onClick={() => void search(Math.max(0, offset - 20))}
          >
            Previous results
          </button>
          <button
            disabled={offset + 20 >= result.total}
            onClick={() => void search(offset + 20)}
          >
            Next results
          </button>
        </>
      )}
    </section>
  );
}
