"""Derived transcript data. Raw Segment and Transcription contracts stay unchanged."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from .schemas import StrictModel


class SpeakerRole(StrEnum):
    DISPATCHER = "DISPATCHER"
    CALLER = "CALLER"
    UNKNOWN = "UNKNOWN"


class SpeakerAssignment(StrictModel):
    speaker_id: str | None = None
    speaker_role: SpeakerRole = SpeakerRole.UNKNOWN
    role_source: Literal["unknown", "text_cue", "speaker_context", "provided_role"] = "unknown"
    # Reserved for a provider with a meaningful confidence measure; local cues
    # are not calibrated probabilities and deliberately return None.
    confidence: float | None = Field(default=None, ge=0, le=1)


class ConversationTurn(SpeakerAssignment):
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    text: str
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)
    segment_indices: list[int]


class Conversation(StrictModel):
    version: str
    source_fingerprint: str
    inference_method: str
    has_speaker_ids: bool
    alignment: Literal["exact", "full_text_fallback"]
    turns: list[ConversationTurn]
