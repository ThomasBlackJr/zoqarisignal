"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  UploadCloud,
  FileAudio,
  X,
  ArrowRight,
  Check,
  ShieldCheck,
} from "lucide-react";
import { useDrive } from "@/components/shell";
import { ScorecardPicker } from "@/components/scorecard-picker";
import { ErrorBox } from "@/components/ui";

export default function UploadPage() {
  const { config } = useDrive();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [rubricId, setRubricId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  function choose(candidate?: File) {
    if (!candidate || progress !== null) return;
    setError("");
    if (!/\.(wav|mp3|m4a)$/i.test(candidate.name)) {
      setError("Choose a WAV, MP3, or M4A recording.");
      return;
    }
    if (
      candidate.size > config.max_upload_mb * 1024 * 1024 ||
      candidate.size === 0
    ) {
      setError(`Choose a nonempty recording under ${config.max_upload_mb} MB.`);
      return;
    }
    setFile(candidate);
  }
  function upload() {
    if (!file || !rubricId) return;
    setProgress(0);
    setError("");
    const request = new XMLHttpRequest();
    request.open("POST", "/api/calls");
    request.setRequestHeader("X-Drive-Request", "1");
    request.timeout = 180000;
    request.upload.onprogress = (e) => {
      if (e.lengthComputable)
        setProgress(Math.round((e.loaded / e.total) * 100));
    };
    request.onload = () => {
      let data;
      try {
        data = JSON.parse(request.responseText);
      } catch {
        data = null;
      }
      if (request.status === 201) router.push(`/calls/${data.id}`);
      else {
        setError(
          typeof data?.detail === "string"
            ? data.detail
            : "Upload failed. Please try again.",
        );
        setProgress(null);
        if (request.status === 401) router.replace("/login");
      }
    };
    request.onerror = request.ontimeout = () => {
      setError(
        "The upload connection was interrupted. Check the call library before trying again.",
      );
      setProgress(null);
    };
    const body = new FormData();
    body.append("file", file);
    body.append("rubric_id", rubricId);
    request.send(body);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">NEW RECORDING</div>
          <h1>Upload a call</h1>
          <p>Turn a customer interaction into an actionable quality review.</p>
        </div>
        <Link className="button secondary" href="/batches">
          Upload multiple recordings
        </Link>
      </div>
      <div className="upload-layout">
        <section className="panel upload-panel">
          <h2>Call recording</h2>
          <ScorecardPicker
            value={rubricId}
            onChange={setRubricId}
            disabled={progress !== null}
          />
          <p className="muted">Add one audio recording to begin.</p>
          <input
            ref={input}
            className="sr-only"
            type="file"
            accept=".wav,.mp3,.m4a"
            aria-label="Choose audio recording"
            disabled={progress !== null}
            onChange={(e) => choose(e.target.files?.[0])}
          />
          <button
            type="button"
            disabled={progress !== null}
            className={`dropzone ${drag ? "drag" : ""}`}
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              if (e.dataTransfer.files.length > 1)
                setError("Upload one recording at a time.");
              else choose(e.dataTransfer.files[0]);
            }}
          >
            <span className="upload-cloud">
              <UploadCloud size={34} />
            </span>
            <strong>Drop your recording here</strong>
            <span>
              or <b>browse files</b> on your computer
            </span>
            <small>WAV, MP3, M4A · Up to {config.max_upload_mb} MB</small>
          </button>
          {file && (
            <div className="selected-file">
              <FileAudio size={25} />
              <span>
                <strong>{file.name}</strong>
                <small>
                  {(file.size / 1024 / 1024).toFixed(2)} MB · Ready to upload
                </small>
              </span>
              <button
                className="icon-link"
                aria-label="Remove selected file"
                disabled={progress !== null}
                onClick={() => {
                  setFile(null);
                  if (input.current) input.current.value = "";
                }}
              >
                <X size={18} />
              </button>
            </div>
          )}
          {error && <ErrorBox message={error} />}
          {progress !== null && (
            <div className="upload-progress" role="status">
              <span>
                {progress === 100
                  ? "Upload received. Validating recording…"
                  : `Uploading… ${progress}%`}
              </span>
              <progress max={100} value={progress} />
            </div>
          )}
          <div className="upload-actions">
            <span>
              <ShieldCheck size={16} />
              Only workspace users can access recordings.
            </span>
            <button
              className="button primary"
              onClick={upload}
              disabled={!file || !rubricId || progress !== null}
            >
              {progress !== null ? "Uploading…" : "Upload & process"}
              <ArrowRight size={17} />
            </button>
          </div>
        </section>
        <aside className="process-guide">
          <div className="eyebrow">WHAT HAPPENS NEXT</div>
          <h2>
            A clearer view,
            <br />
            in three steps.
          </h2>
          {[
            {
              title: "Transcribe",
              text: "Convert the conversation into a readable transcript.",
            },
            {
              title: "Evaluate",
              text: "Evaluate the interaction against your selected scorecard.",
            },
            {
              title: "Review",
              text: "Listen, read, and explore strengths and coaching opportunities.",
            },
          ].map((step, i) => (
            <div className="guide-step" key={step.title}>
              <span>{i + 1}</span>
              <div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </div>
            </div>
          ))}
          <p className="guide-note">
            <Check size={16} />
            You can leave the page while processing continues.
          </p>
        </aside>
      </div>
    </>
  );
}
