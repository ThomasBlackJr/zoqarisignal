from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import Role


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class NewUser(Login):
    name: str = Field(min_length=1, max_length=100)
    role: Role = Role.SUPERVISOR

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if len(value) < 12:
            raise ValueError("Use at least 12 characters")
        return value

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        value = value.strip().lower()
        if "@" not in value or any(c.isspace() for c in value):
            raise ValueError("Enter an email address")
        return value


class Segment(StrictModel):
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    text: str = Field(min_length=1)
    speaker: str | None = None

    @model_validator(mode="after")
    def times(self):
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("Segment end precedes start")
        return self


class Transcription(StrictModel):
    text: str = Field(min_length=1)
    segments: list[Segment] = Field(default_factory=list)
    duration: float | None = Field(default=None, ge=0)

    @field_validator("text")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("No speech was returned")
        return value


class Category(StrictModel):
    key: str
    score: int = Field(ge=0, le=100, strict=True)
    max_score: int = Field(ge=1, le=100, strict=True)
    explanation: str = Field(min_length=1)
    evidence: list[str]


class QAResult(StrictModel):
    overall_score: int = Field(ge=0, le=100, strict=True)
    categories: list[Category]
    summary: str = Field(min_length=1)
    strengths: list[str]
    coaching_opportunities: list[str]
