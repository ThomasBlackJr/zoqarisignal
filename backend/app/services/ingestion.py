"""Shared audio ingestion. Batch entries point to the normal Call/processing pipeline."""

import hashlib
import re
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, update
from ..models import Call, Organization, identifier
from .audio import MIME, save_upload
from .rubric import selected_rubric
from .flags import audit_reference


def clean_filename(value):
    return re.sub(r"[\x00-\x1f\x7f]", "", (value or "").replace("\\", "/").split("/")[-1])[:255]


def file_error(filename, size, limit):
    if Path(filename).suffix.lower() not in MIME:
        return "Choose a WAV, MP3, or M4A recording"
    if size <= 0 or size > limit:
        return "Choose a nonempty recording within the configured file size limit"
    return None


async def ingest(upload, user, settings, db, is_demo, item=None, lease=None, rubric_id=None):
    rubric = selected_rubric(db, user.organization_id, rubric_id)
    filename = clean_filename(upload.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in MIME:
        await upload.close()
        raise HTTPException(422, "Choose a WAV, MP3, or M4A recording")
    call_id = identifier()
    storage = call_id + suffix
    path = settings.upload_dir / storage
    size, duration = await save_upload(upload, path, settings.max_upload_mb * 1024 * 1024)
    try:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        # Serialize dedup decision + insert within this tenant, including competing requests.
        db.execute(update(Organization).where(Organization.id == user.organization_id).values(id=Organization.id))
        if item:
            db.refresh(item)
            if item.call_id or item.status != "uploading" or item.updated_at != lease:
                raise HTTPException(409, "This upload attempt was replaced. Refresh the batch.")
        existing = (
            db.scalar(
                select(Call)
                .where(Call.organization_id == user.organization_id, Call.content_sha256 == digest)
                .order_by(Call.created_at, Call.id)
                .limit(1)
            )
            if item
            else None
        )
        if existing:
            effective_id = existing.requested_rubric_id or (
                existing.evaluation.rubric_id if existing.evaluation else None
            )
            if effective_id != rubric.id:
                raise HTTPException(
                    409,
                    "This recording exists with a different scorecard. Open the existing interaction and choose New QA evaluation, or select its scorecard for this batch.",
                )
        call = existing or Call(
            id=call_id,
            filename=filename,
            storage_name=storage,
            content_type=MIME[suffix],
            size_bytes=size,
            duration=duration,
            uploaded_by=user.id,
            organization_id=user.organization_id,
            is_demo=is_demo,
            content_sha256=digest,
            requested_rubric_id=rubric.id,
        )
        if not existing:
            db.add(call)
            audit_reference(db, call)
        if item:
            item.call_id = call.id
            item.duplicate = existing is not None
            item.status = "accepted"
            item.error = None
        db.commit()
        if existing:
            path.unlink(missing_ok=True)
        return call
    except BaseException:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
