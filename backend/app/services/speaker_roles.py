"""Conservative, offline role hints; never claims to perform audio diarization."""

import re
from typing import Mapping, Protocol

from ..conversation_schemas import SpeakerAssignment, SpeakerRole
from ..schemas import Segment


class SpeakerRoleService(Protocol):
    name: str

    def infer(self, segments: list[Segment]) -> list[SpeakerAssignment]: ...


def speaker_id(value: str | None) -> str | None:
    if not value or value.strip().casefold() in {"", "unknown", "unidentified", "?"}:
        return None
    return value  # Preserve a supplied ID; never manufacture one from its order.


INTRO = r"(?:(?:hello|hi|good morning|good afternoon|good evening)[,!\.\s]*)?"
DISPATCH = re.compile(
    r"^" + INTRO + r"(?:thank(?: you|s) for calling\b|how (?:can|may) i help\b|"
    r"(?:can|could|may) i (?:please )?(?:get|have|confirm) your (?:route|tracking|delivery|order)\b|"
    r"(?:i am|i'm) (?:the |your |a )?dispatcher\b)",
    re.IGNORECASE,
)
CALLER = re.compile(
    r"^" + INTRO + r"(?:(?:i am|i'm) (?:calling (?:because|about|regarding)\b|checking on (?:my |a |the )?delivery\b)|"
    r"(?:i am|i'm) (?:the |your |a )?(?:driver|customer)\b|my delivery (?:has not|hasn't|isn't|is not)\b)",
    re.IGNORECASE,
)


def cue_roles(text: str) -> set[SpeakerRole]:
    roles = set()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text.strip()):
        if DISPATCH.search(sentence.strip()):
            roles.add(SpeakerRole.DISPATCHER)
        if CALLER.search(sentence.strip()):
            roles.add(SpeakerRole.CALLER)
    return roles


class LocalSpeakerRoles:
    name = "local-text-cues-v1"

    def __init__(self, known_roles: Mapping[str, SpeakerRole] | None = None):
        # Future adapters may supply an explicit, trustworthy ID-to-role map.
        # An ID such as speaker_0 alone says nothing about the speaker's role.
        self.known_roles = dict(known_roles or {})

    def infer(self, segments: list[Segment]) -> list[SpeakerAssignment]:
        cues = [cue_roles(segment.text) for segment in segments]
        per_speaker: dict[str, set[SpeakerRole]] = {}
        for segment, roles in zip(segments, cues):
            identity = speaker_id(segment.speaker)
            if identity is not None:
                per_speaker.setdefault(identity, set()).update(roles)
        results = []
        for segment, roles in zip(segments, cues):
            identity = speaker_id(segment.speaker)
            if identity is not None and identity in self.known_roles:
                role = self.known_roles[identity]
                source = "provided_role" if role != SpeakerRole.UNKNOWN else "unknown"
            else:
                relevant = per_speaker[identity] if identity is not None else roles
                # Mixed role cues can indicate several people inside one raw
                # segment, quotations, or incorrect speaker IDs. Do not guess.
                role = next(iter(relevant)) if len(relevant) == 1 else SpeakerRole.UNKNOWN
                source = (
                    "unknown" if role == SpeakerRole.UNKNOWN else "text_cue" if role in roles else "speaker_context"
                )
            results.append(SpeakerAssignment(speaker_id=identity, speaker_role=role, role_source=source))
        return results
