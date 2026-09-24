"use client";
import Link from "next/link";
import Image from "next/image";
import { ArrowUpRight, Headphones, Upload, LoaderCircle } from "lucide-react";
import { Call, date, duration } from "@/lib/api";

export function Brand() {
  return (
    <div className="signal-brand">
      <Image
        src="/brand/z-mark.png"
        width={120}
        height={134}
        className="signal-mark"
        alt=""
        priority
      />
      <span>
        <Image
          src="/brand/wordmark.png"
          width={356}
          height={53}
          className="signal-wordmark"
          alt="ZOQARI"
          priority
        />
        <span className="signal-product">SIGNAL</span>
      </span>
    </div>
  );
}
export function Status({ status }: { status: string }) {
  return (
    <span className={`status ${status}`}>
      <span />
      {status === "queued"
        ? "Awaiting processing"
        : status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}
export function Loading() {
  return (
    <div className="empty" role="status">
      <LoaderCircle className="spin" size={28} />
      <p>Loading Signal…</p>
    </div>
  );
}
export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="error" role="alert">
      {message}
    </div>
  );
}
export function UploadLink() {
  return (
    <Link className="button primary" href="/upload">
      <Upload size={17} />
      Upload call
    </Link>
  );
}
export function CallTable({ calls }: { calls: Call[] }) {
  if (!calls.length)
    return (
      <div className="empty">
        <div className="empty-icon">
          <Headphones size={28} />
        </div>
        <h3>No calls to show</h3>
        <p>Upload a recording to start reviewing interaction quality.</p>
        <UploadLink />
      </div>
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Recording / Call ID</th>
            <th>Uploaded</th>
            <th>Assigned employee</th>
            <th>Duration</th>
            <th>Status</th>
            <th>Signal Score</th>
            <th>
              <span className="sr-only">Open call</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {calls.map((call) => (
            <tr key={call.id}>
              <td>
                <Link className="recording" href={`/calls/${call.id}`}>
                  <span className="audio-icon">
                    <Headphones size={19} />
                  </span>
                  <span>
                    <strong>{call.filename}</strong>
                    <small>{call.audit_number}{call.flagged ? " · Flagged" : ""}</small>
                    <small>
                      {call.id.slice(0, 8).toUpperCase()}
                      {call.is_demo ? " · DEMO" : ""}
                    </small>
                  </span>
                </Link>
              </td>
              <td className="muted nowrap">{date(call.created_at)}</td>
              <td>
                {call.employee_id ? (
                  <Link href={"/employees/" + call.employee_id}>
                    {call.employee_name}
                  </Link>
                ) : (
                  "Unassigned"
                )}
              </td>
              <td className="mono">{duration(call.duration)}</td>
              <td>
                <Status status={call.status} />
                {call.evaluation_stale && (
                  <small className="table-review">Outdated evaluation</small>
                )}
                {call.review_status === "needs_review" && (
                  <small className="table-review">Needs review</small>
                )}
                {call.review_status === "reviewed" && (
                  <small className="table-review reviewed">Reviewed</small>
                )}
              </td>
              <td>
                <span
                  className={`score-pill ${call.qa_score === null ? "unscored" : ""}`}
                >
                  {call.qa_score ?? "—"}
                </span>
                {call.qa_score !== null && (
                  <span className="score-max"> / 100</span>
                )}
                {call.has_overrides && (
                  <small className="table-review">
                    Adjusted · AI {call.ai_score}
                  </small>
                )}
              </td>
              <td>
                <Link
                  href={`/calls/${call.id}`}
                  className="icon-link"
                  aria-label={`Open ${call.filename}`}
                >
                  <ArrowUpRight size={18} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
