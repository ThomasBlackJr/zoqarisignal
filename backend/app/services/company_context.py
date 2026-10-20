"""Tenant-local vocabulary and conservative display annotations; raw evidence is immutable."""

import json
import re
from difflib import SequenceMatcher
from pydantic import Field, field_validator
from ..schemas import StrictModel


class Vocabulary(StrictModel):
    preferred_name: str | None = Field(default=None, max_length=120)
    alternate_names: list[str] = Field(default_factory=list, max_length=20)
    abbreviations: list[str] = Field(default_factory=list, max_length=20)
    pronunciations: list[str] = Field(default_factory=list, max_length=20)
    industry_terms: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("alternate_names", "abbreviations", "pronunciations", "industry_terms")
    @classmethod
    def bounded_terms(cls, value):
        if any(not term.strip() or len(term) > 120 or any(ord(c) < 32 for c in term) for term in value):
            raise ValueError("Use nonblank vocabulary terms of at most 120 characters")
        return list(dict.fromkeys(term.strip() for term in value))


def vocabulary(organization):
    data = Vocabulary.model_validate(organization.transcription_vocabulary or {}).model_dump()
    data["registered_name"] = organization.name
    return data


def provider_prompt(context):
    # No shared mutable prompt/cache; this context is built from the call's own tenant.
    terms = [context.get("preferred_name"), context["registered_name"]]
    for key in ("alternate_names", "abbreviations", "pronunciations", "industry_terms"):
        terms.extend(context.get(key, []))
    selected = []
    for term in terms:
        if term and term not in selected and len(json.dumps(selected + [term], ensure_ascii=False)) < 600:
            selected.append(term)
    return "Possible spoken vocabulary (use only if actually spoken): " + json.dumps(selected, ensure_ascii=False)


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def soundex(word):
    word = re.sub("[^a-z]", "", word.casefold())
    if not word:
        return ""
    groups = {c: str(i) for i, letters in enumerate(["bfpv", "cgjkqsxz", "dt", "l", "mn", "r"], 1) for c in letters}
    output = word[0]
    previous = groups.get(word[0], "")
    for char in word[1:]:
        digit = groups.get(char, "")
        if digit and digit != previous:
            output += digit
        previous = digit
    return (output + "000")[:4]


def company_annotations(text, context):
    target = (context.get("preferred_name") or context["registered_name"]).strip()
    names = list(
        dict.fromkeys(
            [
                target,
                context["registered_name"],
                *context.get("alternate_names", []),
                *context.get("abbreviations", []),
                *context.get("pronunciations", []),
            ]
        )
    )
    output = []
    # Require a direct business greeting and stop at a sentence/intro boundary.
    pattern = (
        r"\b(?:thank you|thanks) for calling\s+([^.!?\n,;]{2,120}?)(?=[.!?\n,;]|\s+(?:this is|how (?:can|may))\b|$)"
    )
    for match in re.finditer(pattern, text, re.I):
        candidate = match.group(1).strip()
        if normalized(candidate) == normalized(target):
            continue
        accepted = False
        score = 0.0
        for name in names:
            left = re.findall(r"[a-z0-9]+", candidate.casefold())
            right = re.findall(r"[a-z0-9]+", name.casefold())
            if normalized(candidate) == normalized(name):
                accepted = True
                score = 1.0
                break
            if len(left) < 2 or len(left) != len(right) or left[0] != right[0] or len(left[0]) < 3:
                continue
            text_score = SequenceMatcher(None, normalized(candidate), normalized(name)).ratio()
            phonetic = SequenceMatcher(None, " ".join(map(soundex, left)), " ".join(map(soundex, right))).ratio()
            if text_score >= 0.68 and phonetic >= 0.90:
                accepted = True
                score = max(score, (text_score + phonetic) / 2)
        if accepted:
            start = match.start(1)
            output.append(
                {
                    "source_start": start,
                    "source_end": start + len(candidate),
                    "original": candidate,
                    "replacement": target,
                    "method": "greeting+lexical+phonetic-v1",
                    "similarity": round(score, 3),
                    "registered_name": context["registered_name"],
                }
            )
    return output
