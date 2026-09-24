"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, date } from "@/lib/api";
import { ScorecardPicker } from "./scorecard-picker";
import { ErrorBox, Loading } from "./ui";
import { useDrive } from "./shell";

type Item = {
  id: string;
  filename: string;
  size_bytes: number;
  status: string;
  error: string | null;
  call_id: string | null;
  duplicate: boolean;
};
type Batch = {
  scorecard: string;
  id: string;
  created_at: number;
  counts: {
    total: number;
    completed: number;
    processing: number;
    queued: number;
    failed: number;
    awaiting_upload: number;
    duplicates: number;
    deleted: number;
  };
  items: Item[];
};

export function BatchUpload() {
  const { config } = useDrive();
  const [rubricId, setRubricId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [batches, setBatches] = useState<Batch[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const requestKey = useRef<string | null>(null);
  const mounted = useRef(true);
  const input = useRef<HTMLInputElement>(null);
  const refresh = useCallback(async () => {
    const result = await api<{ items: Batch[]; total: number }>(
      "/batches?offset=" + offset,
    );
    if (mounted.current) {
      setBatches(result.items);
      setTotal(result.total);
    }
  }, [offset]);
  useEffect(() => {
    mounted.current = true;
    void refresh().catch((e) => setError(e.message));
    const timer = setInterval(() => {
      void refresh().catch((e) => {
        if (mounted.current) setError(e.message);
      });
    }, 2500);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [refresh]);
  function select(values: FileList | File[]) {
    if (running) return;
    const selected = Array.from(values);
    if (selected.length > 100) {
      setError("Select up to 100 recordings per batch.");
      return;
    }
    setFiles(selected);
    requestKey.current = null;
    setError("");
  }
  function upload(batchId: string, itemId: string, file: File) {
    return new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(
        "POST",
        "/api/batches/" + batchId + "/items/" + itemId + "/upload",
      );
      xhr.setRequestHeader("X-Drive-Request", "1");
      xhr.timeout = 180000;
      xhr.upload.onprogress = (e) => {
        if (mounted.current && e.lengthComputable)
          setProgress((p) => ({
            ...p,
            [itemId]: Math.round((e.loaded / e.total) * 100),
          }));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else {
          let message =
            "Upload request failed. Refresh the batch and retry this file.";
          try {
            const body = JSON.parse(xhr.responseText);
            if (typeof body.detail === "string") message = body.detail;
          } catch {}
          reject(new Error(message));
        }
      };
      xhr.onerror = xhr.ontimeout = () =>
        reject(
          new Error(
            "Transfer interrupted. Received recordings continue processing; reselect missing files when the transfer lease expires.",
          ),
        );
      const body = new FormData();
      body.append("file", file);
      xhr.send(body);
    });
  }
  async function submit() {
    if (!files.length || !rubricId || running) return;
    setRunning(true);
    setError("");
    requestKey.current ??= crypto.randomUUID();
    try {
      const batch = await api<Batch>("/batches", {
        method: "POST",
        body: JSON.stringify({
          request_key: requestKey.current,
          rubric_id: rubricId,
          files: files.map((f) => ({ filename: f.name, size_bytes: f.size })),
        }),
      });
      await refresh();
      // Bounded transfers isolate failures. Server processing is independent once each file is received.
      for (let start = 0; start < batch.items.length; start += 2) {
        const results = await Promise.allSettled(
          batch.items
            .slice(start, start + 2)
            .map((item, j) =>
              item.call_id || item.status === "failed"
                ? Promise.resolve()
                : upload(batch.id, item.id, files[start + j]),
            ),
        );
        const failed = results.find((r) => r.status === "rejected");
        if (failed?.status === "rejected" && mounted.current)
          setError((failed.reason as Error).message);
        await refresh();
      }
      if (mounted.current) {
        setFiles([]);
        requestKey.current = null;
      }
    } catch (e) {
      if (mounted.current) setError((e as Error).message);
    } finally {
      if (mounted.current) setRunning(false);
    }
  }
  async function replace(batchId: string, item: Item, file?: File) {
    if (!file || running) return;
    setRunning(true);
    setError("");
    try {
      await upload(batchId, item.id, file);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }
  async function retry(item: Item) {
    setError("");
    try {
      await api("/calls/" + item.call_id + "/retry", { method: "POST" });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">BATCH INGESTION</div>
          <h1>Bulk upload</h1>
          <p>A persistent queue for your interaction volume.</p>
        </div>
        <Link className="button secondary" href="/upload">
          Single recording
        </Link>
      </div>
      <section className="panel batch-create">
        <h2>Add recordings</h2>
        <ScorecardPicker
          value={rubricId}
          onChange={(id) => {
            setRubricId(id);
            requestKey.current = null;
          }}
          disabled={running}
        />

        <p>
          Up to 100 files per batch · WAV, MP3, M4A · {config.max_upload_mb} MB
          each.
        </p>
        <input
          className="sr-only"
          type="file"
          multiple
          ref={input}
          aria-label="Choose batch recordings"
          disabled={running}
          onChange={(e) => e.target.files && select(e.target.files)}
        />
        <button
          className="dropzone batch-drop"
          disabled={running}
          onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            select(e.dataTransfer.files);
          }}
        >
          <strong>Drop multiple recordings here</strong>
          <span>or browse files</span>
        </button>
        {!!files.length && (
          <>
            <p>
              {files.length} files selected. Invalid files receive their own
              failure state; valid recordings continue.
            </p>
            <ul className="batch-selection">
              {files.map((f, i) => (
                <li key={i}>
                  {f.name}{" "}
                  <small>
                    {(f.size / 1048576).toFixed(2)} MB
                    {!/\.(wav|mp3|m4a)$/i.test(f.name) ||
                    f.size === 0 ||
                    f.size > config.max_upload_mb * 1048576
                      ? " · Cannot upload: format or size"
                      : ""}
                  </small>
                </li>
              ))}
            </ul>
          </>
        )}
        <button
          className="button primary"
          disabled={!files.length || !rubricId || running}
          onClick={submit}
        >
          {running ? "Sending recordings…" : "Submit batch"}
        </button>
        <p className="muted">
          Keep this tab open until transfer finishes. After receipt,
          transcription and QA continue on the server even if you leave. Missing
          transfers remain in batch history and can be reselected.
        </p>
      </section>
      {error && <ErrorBox message={error} />}
      <div className="section-heading">
        <h2>Batch history</h2>
        <button
          className="button secondary"
          onClick={() => {
            void refresh().catch((e) => setError(e.message));
          }}
        >
          Refresh batches
        </button>
      </div>
      {!batches ? (
        <Loading />
      ) : !batches.length ? (
        <p className="panel batch-create">
          No batches yet. Submit recordings above to start your first queue.
        </p>
      ) : (
        batches.map((batch) => (
          <section className="panel batch-panel" key={batch.id}>
            <div className="panel-heading">
              <div>
                <h3>{batch.counts.total} recordings</h3>
                <p>
                  {batch.scorecard} · {date(batch.created_at)} · Batch{" "}
                  {batch.id.slice(0, 8)}
                </p>
              </div>
              <span>{batch.counts.duplicates} duplicates linked</span>
            </div>
            <div className="batch-counts" aria-label="Batch progress">
              <span>{batch.counts.completed} Complete</span>
              <span>{batch.counts.processing} Processing</span>
              <span>{batch.counts.queued} Queued</span>
              <span>{batch.counts.failed} Failed</span>
              <span>{batch.counts.deleted} Deleted</span>
              <span>{batch.counts.awaiting_upload} Awaiting upload</span>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Recording</th>
                    <th>State</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>
                          {item.call_id ? (
                            <Link href={"/calls/" + item.call_id}>
                              {item.filename}
                            </Link>
                          ) : (
                            item.filename
                          )}
                        </strong>
                        {item.duplicate && (
                          <small className="batch-note">
                            Exact recording already exists. No extra processing
                            request.
                          </small>
                        )}
                        {item.error && (
                          <small className="batch-error">{item.error}</small>
                        )}
                      </td>
                      <td>
                        <span className={"status " + item.status}>
                          {item.status === "pending"
                            ? "Awaiting upload"
                            : item.status}
                        </span>
                        {item.status === "uploading" &&
                          progress[item.id] !== undefined && (
                            <small>{progress[item.id]}% transferred</small>
                          )}
                      </td>
                      <td>
                        {item.call_id ? (
                          item.status === "failed" ? (
                            <button
                              className="button secondary"
                              onClick={() => retry(item)}
                            >
                              Retry processing
                            </button>
                          ) : (
                            <Link href={"/calls/" + item.call_id}>
                              Review interaction →
                            </Link>
                          )
                        ) : (
                          item.status !== "uploading" &&
                          item.status !== "deleted" && (
                            <label className="button secondary batch-replace">
                              Reselect recording
                              <input
                                type="file"
                                aria-label={"Replace " + item.filename}
                                disabled={running}
                                onChange={(e) => {
                                  void replace(
                                    batch.id,
                                    item,
                                    e.target.files?.[0],
                                  );
                                  e.target.value = "";
                                }}
                              />
                            </label>
                          )
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
      <div className="batch-pagination">
        <button
          className="button secondary"
          disabled={offset === 0 || running}
          onClick={() => setOffset((n) => Math.max(0, n - 20))}
        >
          Newer batches
        </button>
        <span>{total} batches</span>
        <button
          className="button secondary"
          disabled={offset + 20 >= total || running}
          onClick={() => setOffset((n) => n + 20)}
        >
          Older batches
        </button>
      </div>
    </>
  );
}
