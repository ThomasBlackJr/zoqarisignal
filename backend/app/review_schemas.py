"""Validated supervisor commands. No command accepts transcript words or QA totals."""

from typing import Literal
from pydantic import Field, field_validator
from .schemas import StrictModel
from .conversation_schemas import SpeakerRole


class CategoryDraft(StrictModel):
    key: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    weight: int = Field(ge=1, le=100, strict=True)
    criteria: str = Field(min_length=1, max_length=5000)

    @field_validator("name", "criteria")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Required")
        return value.strip()


class RubricDraft(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    categories: list[CategoryDraft] = Field(max_length=30)
    revision: int = Field(default=1, ge=1, strict=True)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Required")
        return value.strip()


class Revision(StrictModel):
    revision: int = Field(ge=1, strict=True)


class SpeakerEdit(StrictModel):
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_start: int = Field(ge=0, strict=True)
    source_end: int = Field(ge=1, strict=True)
    role: SpeakerRole | None
    scope: Literal["turn", "speaker"] = "turn"
    revision: int = Field(ge=0, strict=True)


class ScoreEdit(StrictModel):
    score: int | None = Field(ge=0, le=100, strict=True)
    reason: str = Field(min_length=1, max_length=2000)
    revision: int = Field(ge=0, strict=True)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A reason is required")
        return value.strip()


class Reevaluation(StrictModel):
    use_previous_scorecard: bool = False
    rubric_id: str
    evaluation_id: str
    transcript_revision: int | None = Field(default=None, ge=0, strict=True)
