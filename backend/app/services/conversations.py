"""Lossless, derived conversation formatting independent of transcription and QA."""

import hashlib
import json

from ..conversation_schemas import Conversation, ConversationTurn, SpeakerAssignment, SpeakerRole
from ..logging import event
from ..schemas import Segment
from .speaker_roles import LocalSpeakerRoles, SpeakerRoleService, speaker_id

VERSION = "speaker-turns-v1"


def fingerprint(text: str, segments: list) -> str:
    return hashlib.sha256(json.dumps([text, segments], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def same_speaker(left: SpeakerAssignment, right: SpeakerAssignment) -> bool:
    if left.speaker_role != right.speaker_role:
        return False
    if left.speaker_id is not None or right.speaker_id is not None:
        return left.speaker_id is not None and left.speaker_id == right.speaker_id
    # Under the typical two-party-call model, adjacent explicit hints for the
    # same role can form an inferred turn. UNKNOWN is never an identity.
    return left.speaker_role != SpeakerRole.UNKNOWN


def align(text: str, segments: list[Segment]) -> list[tuple[int, int]] | None:
    spans = []
    cursor = 0
    for segment in segments:
        core = segment.text.strip()
        start = text.find(core, cursor) if core else -1
        if start < 0 or text[cursor:start].strip():
            return None
        end = start + len(core)
        # Include the original inter-segment whitespace. Concatenating all
        # turn.text values must reproduce Transcript.text byte-for-byte.
        spans.append((cursor, end))
        cursor = end
    if text[cursor:].strip() or not spans:
        return None
    spans[-1] = (spans[-1][0], len(text))
    return spans


class ConversationService:
    def __init__(self, roles: SpeakerRoleService | None = None):
        self.roles = roles or LocalSpeakerRoles()

    def fallback(self, text: str, segments: list) -> Conversation:
        return Conversation(
            version=VERSION,
            source_fingerprint=fingerprint(text, segments),
            inference_method=self.roles.name,
            has_speaker_ids=False,
            alignment="full_text_fallback",
            turns=[ConversationTurn(text=text, source_start=0, source_end=len(text), segment_indices=[])]
            if text
            else [],
        )

    def derive(self, text: str, raw_segments: list) -> Conversation:
        segments = [Segment.model_validate(segment) for segment in raw_segments]
        spans = align(text, segments)
        if spans is None:
            return self.fallback(text, raw_segments)
        assignments = self.roles.infer(segments)
        if len(assignments) != len(segments):
            raise ValueError("Role assignment count does not match raw segments")
        turns: list[ConversationTurn] = []
        for index, (segment, assignment, (source_start, source_end)) in enumerate(zip(segments, assignments, spans)):
            assignment = SpeakerAssignment.model_validate(assignment.model_dump())
            if assignment.speaker_id != speaker_id(segment.speaker):
                raise ValueError("Role service must not replace provider speaker IDs")
            previous = turns[-1] if turns else None
            boundary = segments[index - 1] if index else None
            chronological = (
                boundary is None
                or segment.start is None
                or (
                    (boundary.start is None or segment.start >= boundary.start)
                    and (boundary.end is None or segment.start >= boundary.end)
                )
            )
            if previous and chronological and same_speaker(previous, assignment):
                previous.source_end = source_end
                previous.text = text[previous.source_start : source_end]
                previous.end = segment.end  # Unknown end stays unknown; never substitute last start.
                previous.segment_indices.append(index)
                if previous.confidence is not None and assignment.confidence is not None:
                    previous.confidence = min(previous.confidence, assignment.confidence)
                else:
                    previous.confidence = None
                if previous.role_source != assignment.role_source:
                    previous.role_source = "speaker_context"
            else:
                turns.append(
                    ConversationTurn(
                        **assignment.model_dump(),
                        start=segment.start,
                        end=segment.end,
                        text=text[source_start:source_end],
                        source_start=source_start,
                        source_end=source_end,
                        segment_indices=[index],
                    )
                )
        return Conversation(
            version=VERSION,
            source_fingerprint=fingerprint(text, raw_segments),
            inference_method=self.roles.name,
            has_speaker_ids=any(a.speaker_id is not None for a in assignments),
            alignment="exact",
            turns=turns,
        )


def conversation_for(transcript) -> dict:
    """Use a valid cache or derive locally. Never calls a provider or writes on GET."""
    service = ConversationService()
    if transcript.conversation:
        try:
            cached = Conversation.model_validate(transcript.conversation)
            if (
                cached.version == VERSION
                and cached.inference_method == service.roles.name
                and cached.source_fingerprint == fingerprint(transcript.text, transcript.segments)
                and "".join(turn.text for turn in cached.turns) == transcript.text
            ):
                return cached.model_dump(mode="json")
        except (TypeError, ValueError):
            pass
    try:
        return service.derive(transcript.text, transcript.segments).model_dump(mode="json")
    except Exception as exc:
        event("conversation_derivation_failed", transcript.call_id, error_type=type(exc).__name__)
        return service.fallback(transcript.text, transcript.segments).model_dump(mode="json")
