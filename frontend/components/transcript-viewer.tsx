"use client";

import { useState } from "react";
import { SpeakerControl } from "./speaker-control";
import { FileText } from "lucide-react";
import { ConversationTurn, Detail, duration } from "@/lib/api";

const time = (seconds: number) => duration(seconds).padStart(5, "0");

function TurnTime({
  start,
  end,
  onSeek,
}: {
  start: number | null;
  end: number | null;
  onSeek: (seconds: number) => void;
}) {
  const label =
    start === null
      ? end === null
        ? "Time unavailable"
        : `Start unavailable – ${time(end)}`
      : end === null
        ? `${time(start)} · End unavailable`
        : `${time(start)} – ${time(end)}`;
  return start === null ? (
    <span className="turn-time unavailable">{label}</span>
  ) : (
    <button
      className="timestamp turn-time"
      onClick={() => onSeek(start)}
      aria-label={`Play from ${time(start)}`}
    >
      {label}
    </button>
  );
}

export function TranscriptViewer({
  transcript,
  isDemo,
  failed,
  onSeek,
  callId,
  onSaved,
}: {
  callId?: string;
  onSaved?: () => Promise<void>;
  transcript: Detail["transcript"];
  isDemo: boolean;
  failed: boolean;
  onSeek: (seconds: number) => void;
}) {
  const [raw, setRaw] = useState(false);
  const conversation = transcript?.conversation;
  const fallback: ConversationTurn[] = transcript
    ? [
        {
          start: null,
          end: null,
          text: transcript.text,
          speaker_id: null,
          speaker_role: "UNKNOWN",
          role_source: "unknown",
          confidence: null,
          source_start: 0,
          source_end: transcript.text.length,
          segment_indices: [],
        },
      ]
    : [];
  const turns = conversation?.turns ?? fallback;
  return (
    <section className="panel transcript-panel">
      <div className="panel-heading">
        <div>
          <h2>
            <FileText size={18} />
            Transcript
          </h2>
          <p>
            {transcript
              ? "Conversation record"
              : "Available after transcription"}
          </p>
        </div>
        {transcript && (
          <span className="subtle-tag">
            {isDemo ? "SYNTHETIC" : "TRANSCRIBED"}
          </span>
        )}
      </div>
      {transcript ? (
        <>
          <div
            className="transcript-controls"
            role="group"
            aria-label="Transcript display"
          >
            <button aria-pressed={!raw} onClick={() => setRaw(false)}>
              Conversation
            </button>
            <button aria-pressed={raw} onClick={() => setRaw(true)}>
              Raw segments
            </button>
          </div>
          {!raw && (
            <p className="transcript-disclosure">
              {conversation?.has_speaker_ids
                ? "Speaker IDs supplied by the transcription provider. "
                : "Audio speaker separation is unavailable. "}
              Role labels inferred from wording are tentative. Unknown means
              there is not enough information.
              {conversation?.alignment === "full_text_fallback" &&
                " Showing the original text because reliable segment boundaries are unavailable."}
            </p>
          )}
          <div className="transcript-body">
            {raw ? (
              transcript.segments.length ? (
                transcript.segments.map((segment, i) => (
                  <div className="segment raw-segment" key={i}>
                    <TurnTime
                      start={segment.start}
                      end={segment.end}
                      onSeek={onSeek}
                    />
                    <div>
                      {segment.speaker && (
                        <strong className="speaker">
                          Provider speaker: {segment.speaker}
                        </strong>
                      )}
                      <p className="verbatim-text">{segment.text}</p>
                    </div>
                  </div>
                ))
              ) : (
                <p className="plain-transcript">{transcript.text}</p>
              )
            ) : (
              turns.map((turn, i) => (
                <article
                  className={`conversation-turn ${(turn.effective_role ?? turn.speaker_role).toLowerCase()}`}
                  key={`${turn.source_start}-${i}`}
                >
                  <div className="turn-heading">
                    <TurnTime
                      start={turn.start}
                      end={turn.end}
                      onSeek={onSeek}
                    />
                    {callId && onSaved && conversation?.source_fingerprint ? (
                      <SpeakerControl
                        callId={callId}
                        turn={turn}
                        conversation={conversation}
                        onSaved={onSaved}
                      />
                    ) : (
                      <span
                        className={`speaker-role ${(turn.effective_role ?? turn.speaker_role).toLowerCase()}`}
                      >
                        {turn.effective_role ?? turn.speaker_role}
                      </span>
                    )}
                    {turn.role_source === "text_cue" ||
                    turn.role_source === "speaker_context" ? (
                      <span className="role-origin">Inferred</span>
                    ) : turn.role_source === "provided_role" ? (
                      <span className="role-origin">Provided role</span>
                    ) : null}
                  </div>
                  {turn.speaker_id !== null && (
                    <span className="turn-speaker-id">
                      Speaker ID: {turn.speaker_id}
                    </span>
                  )}
                  <p className="turn-text verbatim-text">{turn.text}</p>
                </article>
              ))
            )}
          </div>
          {!!conversation?.history?.length && (
            <details className="audit-history">
              <summary>
                Speaker correction history ({conversation.history.length})
              </summary>
              {[...conversation.history].reverse().map((h) => (
                <p key={h.id}>
                  <strong>{h.actor_name}</strong> ·{" "}
                  {new Date(h.corrected_at * 1000).toLocaleString()}
                  <br />
                  Turn {h.source_start}–{h.source_end}: {h.previous_role} →{" "}
                  {h.corrected_role ?? h.inferred_role} · {h.scope} correction
                </p>
              ))}
            </details>
          )}
          <div className="panel-foot">
            {transcript.provider} · {transcript.model} · Original wording
            preserved
          </div>
        </>
      ) : (
        <div className="empty">
          <FileText size={30} />
          <h3>Transcript pending</h3>
          <p>
            {failed
              ? "Retry processing to generate the transcript."
              : "Your conversation will appear here once it is ready."}
          </p>
        </div>
      )}
    </section>
  );
}
