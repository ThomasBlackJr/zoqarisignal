"use client";
import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw, Headphones } from "lucide-react";
import { api, busy, date, Detail, duration } from "@/lib/api";
import { ErrorBox, Loading, Status } from "@/components/ui";
import { AdminControls } from "@/components/admin-controls";
import { QAReview } from "@/components/qa-review";
import { FlagEvidence } from "@/components/flags";
import { TranscriptViewer } from "@/components/transcript-viewer";
import { EmployeeAssignment } from "@/components/employee-assignment";

export default function DetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [refresh, setRefresh] = useState(0);
  async function reload() {
    setCall(await api<Detail>(`/calls/${id}`));
    setRefresh((v) => v + 1);
  }
  const audio = useRef<HTMLAudioElement>(null);
  const [call, setCall] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [audioError, setAudioError] = useState(false);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await api<Detail>(`/calls/${id}`);
        if (alive) {
          setCall(value);
          setError("");
          if (busy(value.status)) timer = setTimeout(load, 1800);
        }
      } catch (e) {
        if (alive) {
          setError((e as Error).message);
          timer = setTimeout(load, 5000);
        }
      }
    }
    void load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id, retrying, refresh]);
  async function retry() {
    setRetrying(true);
    try {
      await api(`/calls/${id}/retry`, { method: "POST" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRetrying(false);
    }
  }
  function seek(seconds: number) {
    if (audio.current) {
      audio.current.currentTime = seconds;
      void audio.current.play().catch(() => setAudioError(true));
    }
  }
  if (!call)
    return (
      <>
        {error && <ErrorBox message={error} />}
        <Loading />
      </>
    );
  const qa = call.evaluation;
  return (
    <>
      <Link href="/calls" className="back-link">
        <ArrowLeft size={16} />
        Back to calls
      </Link>
      <div className="page-heading detail-heading">
        <div>
          <div className="eyebrow">
            CALL REVIEW{" "}
            <span className="mono">/ {call.id.slice(0, 8).toUpperCase()}</span>
          </div>
          <h1>{call.filename}</h1>
          <p>
            {call.audit_number}
            {call.flagged && " · Flagged terms detected"}
          </p>
          <p>
            {date(call.created_at)} <span>·</span> {duration(call.duration)}{" "}
            <span>·</span> {(call.size_bytes / 1024 / 1024).toFixed(2)} MB
          </p>
        </div>
        <Status status={call.status} />
      </div>
      {error && <ErrorBox message={error} />}
      {call.is_demo && (
        <div className="notice">
          This call contains a synthetic example transcript and QA evaluation.
          The player contains your original recording; the example text will not
          match its audio.
        </div>
      )}
      {busy(call.status) && (
        <div className="processing-strip" role="status">
          <RefreshCw className="spin" size={18} />
          <strong>
            {call.status === "queued"
              ? "Awaiting processing"
              : call.status === "transcribing"
                ? "Transcribing recording"
                : "Analyzing service quality"}
          </strong>
          <span>This page updates automatically.</span>
        </div>
      )}
      {call.status === "failed" && (
        <div className="failure-panel">
          <ErrorBox message={call.error || "Processing failed"} />
          <button
            className="button secondary"
            onClick={retry}
            disabled={retrying}
          >
            <RefreshCw size={16} />
            {retrying ? "Retrying…" : "Retry processing"}
          </button>
          <small>
            Completed transcription is kept. Retrying may incur provider usage
            charges.
          </small>
        </div>
      )}
      <section className="audio-panel">
        <span className="audio-icon">
          <Headphones size={24} />
        </span>
        <div>
          <strong>Original recording</strong>
          <small>{duration(call.duration)} total duration</small>
        </div>
        <audio
          ref={audio}
          controls
          preload="metadata"
          src={`/api/calls/${id}/audio`}
          onError={() => setAudioError(true)}
        />
        {audioError && (
          <p role="alert">
            Audio could not be played. Check your session or recording format.
          </p>
        )}
      </section>
      <EmployeeAssignment
        callId={id}
        employeeId={call.employee_id}
        employeeName={call.employee_name}
        revision={call.assignment_revision}
        onSaved={reload}
      />
      <div className="detail-grid">
        <FlagEvidence
          callId={call.id}
          revision={call.transcript?.conversation?.revision ?? 0}
          onSeek={seek}
        />
        <TranscriptViewer
          transcript={call.transcript}
          isDemo={call.is_demo}
          failed={call.status === "failed"}
          onSeek={seek}
          callId={id}
          onSaved={reload}
        />
        <QAReview
          qa={qa}
          callId={id}
          onSaved={reload}
          processing={busy(call.status)}
        />
      </div>
      <AdminControls
        kind="call"
        id={id}
        processing={["transcribing", "analyzing"].includes(call.status)}
      />
    </>
  );
}
