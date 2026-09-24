"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox } from "./ui";

export function FlagEvidence({
  callId,
  revision,
  onSeek,
}: {
  callId: string;
  revision: number;
  onSeek: (s: number) => void;
}) {
  const [history, setHistory] = useState(false);
  const [items, setItems] = useState<
    {
      id: string;
      phrase: string;
      severity: string;
      transcript_revision: number;
      matches: {
        quote: string;
        role: string;
        start: number | null;
        source_start: number;
        source_end: number;
      }[];
    }[]
  >([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    api<{ items: typeof items }>(`/calls/${callId}/flags?history=${history}`)
      .then((v) => {
        if (alive) {
          setItems(v.items);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [callId, revision, history]);
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Flagged terms</h2>
          <p>
            Exact word and phrase matches from your organization’s configured
            rules.
          </p>
        </div>
        <label>
          <input
            type="checkbox"
            checked={history}
            onChange={(e) => setHistory(e.target.checked)}
          />{" "}
          Include detection history
        </label>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="dialog-content">
        {items.length ? (
          items.map((d) => (
            <article key={d.id}>
              <h3>
                {d.phrase} · {d.severity}
              </h3>
              <small>
                {d.transcript_revision === revision
                  ? "Current transcript"
                  : "Historical transcript revision"}{" "}
                · {d.matches.length} occurrences
              </small>
              {d.matches.map((m, i) => (
                <blockquote key={i}>
                  <p>{m.quote}</p>
                  <small>
                    {m.role} · Source characters {m.source_start}–{m.source_end}
                  </small>
                  {m.start !== null && (
                    <button
                      className="button secondary"
                      onClick={() => onSeek(m.start!)}
                    >
                      Play evidence
                    </button>
                  )}
                </blockquote>
              ))}
            </article>
          ))
        ) : (
          <p>
            No matches recorded for{" "}
            {history ? "this interaction" : "the current rules and transcript"}.
            Newly configured rules apply on processing or an administrator’s
            scan of existing transcripts.
          </p>
        )}
      </div>
    </section>
  );
}
