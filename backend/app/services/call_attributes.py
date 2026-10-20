"""Conservative deterministic extraction from source spans, never provider-generated facts."""

import re
import time
import unicodedata
from sqlalchemy import select, update
from ..models import CallAttribute, AttributeEvent, Call
from .conversations import fingerprint, align
from ..schemas import Segment
from .reviews import corrected_conversation

FIELDS = {"customer": "Customer", "address": "Address", "order": "Order #", "hawb": "HAWB"}
IDENTIFIERS = {"order", "hawb"}


def normalize(key, value):
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[\s-]+", "", value) if key in IDENTIFIERS else re.sub(r"\s+", " ", value)


def extract(text, segments, turns):
    patterns = {
        "order": r"\border\b(?:\s+(?:number|no\.?))?\s*(?:is\s+|[:#]\s*)?([A-Za-z0-9][A-Za-z0-9-]{2,63})(?![\w/#-])",
        "hawb": r"\b(?:HAWB|house air ?waybill)\b(?:\s+(?:number|no\.?))?\s*(?:is\s+|[:#]\s*)?([A-Za-z0-9][A-Za-z0-9-]{2,63})(?![\w/#-])",
        "address": r"\b(\d{1,6}\s+(?:[\w\x27’-]+\s+){1,6}(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Boulevard|Blvd)\b(?:,\s*[A-Za-z][A-Za-z -]{0,35}){0,3}(?:\s+\d{5}(?:-\d{4})?)?)",
        "customer": r"\b(?:This is|My name is)\s+([A-Z][a-zA-Z\x27’-]+(?:\s+[A-Z][a-zA-Z\x27’-]+){1,3})(?=\s+(?:calling|and|speaking)|[,.!?]|$)",
    }
    output = {}
    spans = align(text, [Segment.model_validate(s) for s in segments])
    for key, pattern in patterns.items():
        candidates = {}
        for match in re.finditer(pattern, text, 0 if key == "customer" else re.I):
            value = match.group(1).strip()
            start = match.start(1)
            end = start + len(value)
            if len(value) > 500:
                continue
            if key in IDENTIFIERS and (not any(c.isdigit() for c in value) or not value[-1].isalnum()):
                continue
            if key == "customer":
                turn = next((t for t in turns if t["source_start"] <= start < t["source_end"]), {})
                role = turn.get("effective_role", turn.get("speaker_role", "UNKNOWN"))
                if role == "DISPATCHER" or not (role == "CALLER" or text[end:].lstrip().startswith("calling")):
                    continue
            index = next((i for i, (a, b) in enumerate(spans or []) if a <= start < end <= b), None)
            candidates.setdefault(
                normalize(key, value),
                {
                    "value": value,
                    "source_start": start,
                    "source_end": end,
                    "source_segment": index,
                    "timestamp": segments[index].get("start") if index is not None else None,
                },
            )
        # Different plausible values are ambiguous, not a reason to select the first.
        if len(candidates) == 1:
            output[key] = next(iter(candidates.values()))
    return output


def attribute_view(row):
    return {
        k: getattr(row, k)
        for k in (
            "id",
            "key",
            "value",
            "confidence",
            "source_start",
            "source_end",
            "source_segment",
            "timestamp",
            "origin",
            "verified",
            "revision",
            "updated_at",
            "source_fingerprint",
        )
    }


def sync_attributes(db, call):
    if call.transcript is None:
        return
    db.execute(update(Call).where(Call.id == call.id, Call.organization_id == call.organization_id).values(id=Call.id))
    conversation = corrected_conversation(call.transcript, db)
    extracted = extract(call.transcript.text, call.transcript.segments, conversation["turns"])
    source = fingerprint(call.transcript.text, call.transcript.segments)
    current = {
        r.key: r
        for r in db.scalars(
            select(CallAttribute).where(
                CallAttribute.call_id == call.id, CallAttribute.organization_id == call.organization_id
            )
        )
    }
    for key in FIELDS:
        row = current.get(key)
        if row and row.origin == "manual":
            continue  # Includes human removal tombstones.
        data = extracted.get(key, {})
        value = data.get("value")
        if row and row.value == value and row.source_fingerprint == source:
            continue
        old = attribute_view(row) if row else None
        if row is None:
            row = CallAttribute(
                call_id=call.id,
                organization_id=call.organization_id,
                key=key,
                origin="auto",
                verified=False,
                revision=0,
            )
            db.add(row)
        row.value = value
        row.normalized_value = normalize(key, value) if value else None
        row.source_fingerprint = source
        row.confidence = None
        for field in ("source_start", "source_end", "source_segment", "timestamp"):
            setattr(row, field, data.get(field))
        row.updated_at = time.time()
        row.revision += 1
        db.flush()
        db.add(
            AttributeEvent(
                organization_id=call.organization_id,
                call_id=call.id,
                key=key,
                previous=old,
                current=attribute_view(row),
            )
        )
