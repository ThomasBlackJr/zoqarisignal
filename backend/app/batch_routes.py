"""Durable manifests with independent, idempotent per-file ingestion."""

import hashlib
import json
import time
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import Field
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from .auth import get_db, require
from .models import Organization, UploadBatch, UploadItem
from .schemas import StrictModel
from .services.ingestion import clean_filename, file_error, ingest
from .services.rubric import selected_rubric
from .services.entitlements import assert_account_access

router = APIRouter()


class ManifestFile(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0, strict=True)


class Manifest(StrictModel):
    rubric_id: str | None = Field(default=None, max_length=36)
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    files: list[ManifestFile] = Field(min_length=1, max_length=100)


def get_batch(db, batch_id, user):
    batch = db.scalar(
        select(UploadBatch).where(UploadBatch.id == batch_id, UploadBatch.organization_id == user.organization_id)
    )
    if batch is None:
        raise HTTPException(404, "Batch not found")
    return batch


def batch_view(batch):
    items = []
    counts = dict(
        total=len(batch.items),
        completed=0,
        processing=0,
        queued=0,
        failed=0,
        awaiting_upload=0,
        duplicates=0,
        deleted=0,
    )
    for item in batch.items:
        call = item.call
        if call and call.organization_id != batch.organization_id:
            raise RuntimeError("batch_organization_mismatch")
        state = call.status if call else item.status
        error = call.error if call else item.error
        stale = not call and state == "uploading" and item.updated_at < time.time() - 600
        if stale:
            state, error = "failed", "The transfer was interrupted. Reselect the recording to retry."
        if state == "deleted":
            counts["deleted"] += 1
        elif state == "completed":
            counts["completed"] += 1
        elif state == "failed":
            counts["failed"] += 1
        elif state == "queued":
            counts["queued"] += 1
        elif state in {"transcribing", "analyzing", "uploading"}:
            counts["processing"] += 1
        else:
            counts["awaiting_upload"] += 1
        counts["duplicates"] += int(item.duplicate)
        items.append(
            dict(
                id=item.id,
                filename=call.filename if call else item.filename,
                size_bytes=call.size_bytes if call else item.size_bytes,
                status=state,
                error=error,
                call_id=item.call_id,
                duplicate=item.duplicate,
            )
        )
    return dict(
        id=batch.id,
        created_at=batch.created_at,
        counts=counts,
        items=items,
        rubric_id=batch.rubric_id,
        scorecard=(f"{batch.rubric.name} · {batch.rubric.version}" if batch.rubric else "Legacy default"),
    )


@router.post("/batches", status_code=201)
def create_batch(body: Manifest, request: Request, user=Depends(require("review")), db=Depends(get_db)):
    fingerprint = hashlib.sha256(json.dumps([f.model_dump() for f in body.files], sort_keys=True).encode()).hexdigest()
    db.execute(update(Organization).where(Organization.id == user.organization_id).values(id=Organization.id))
    existing = db.scalar(
        select(UploadBatch).where(
            UploadBatch.organization_id == user.organization_id, UploadBatch.request_key == body.request_key
        )
    )
    if existing:
        if existing.manifest_hash != fingerprint or (
            body.rubric_id is not None and body.rubric_id != existing.rubric_id
        ):
            raise HTTPException(409, "This batch key was used for different files. Start a new batch.")
        return batch_view(existing)
    rubric = selected_rubric(db, user.organization_id, body.rubric_id)
    batch = UploadBatch(
        rubric_id=rubric.id,
        organization_id=user.organization_id,
        created_by=user.id,
        request_key=body.request_key,
        manifest_hash=fingerprint,
    )
    limit = request.app.state.settings.max_upload_mb * 1024 * 1024
    for position, file in enumerate(body.files):
        filename = clean_filename(file.filename)
        error = file_error(filename, file.size_bytes, limit)
        batch.items.append(
            UploadItem(
                position=position,
                filename=filename,
                size_bytes=file.size_bytes,
                status="failed" if error else "pending",
                error=error,
            )
        )
    db.add(batch)
    db.commit()
    return batch_view(batch)


@router.get("/batches")
def list_batches(offset: int = Query(0, ge=0), user=Depends(require("review")), db=Depends(get_db)):
    query = select(UploadBatch).where(UploadBatch.organization_id == user.organization_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    batches = db.scalars(
        query.options(selectinload(UploadBatch.items).selectinload(UploadItem.call))
        .order_by(UploadBatch.created_at.desc(), UploadBatch.id)
        .offset(offset)
        .limit(20)
    ).all()
    return {"total": total, "items": [batch_view(batch) for batch in batches]}


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str, user=Depends(require("review")), db=Depends(get_db)):
    return batch_view(get_batch(db, batch_id, user))


@router.post("/batches/{batch_id}/items/{item_id}/upload")
async def upload_item(
    batch_id: str,
    item_id: str,
    request: Request,
    file: UploadFile = File(...),
    user=Depends(require("review")),
    db=Depends(get_db),
):
    batch = get_batch(db, batch_id, user)
    item = next((i for i in batch.items if i.id == item_id), None)
    if item is None:
        await file.close()
        raise HTTPException(404, "Batch item not found")
    if item.status == "deleted":
        await file.close()
        raise HTTPException(409, "This interaction was deleted. Create a new batch to upload again.")
    if item.call_id:
        await file.close()
        return batch_view(batch)
    lease = time.time()
    claimed = db.execute(
        update(UploadItem)
        .where(
            UploadItem.id == item.id,
            UploadItem.call_id.is_(None),
            ((UploadItem.status != "uploading") | (UploadItem.updated_at < time.time() - 600)),
        )
        .values(status="uploading", updated_at=lease, error=None)
    )
    db.commit()
    if claimed.rowcount != 1:
        await file.close()
        raise HTTPException(409, "This file is already uploading. Refresh its status before retrying.")
    try:
        settings = request.app.state.settings
        db.refresh(user.organization)
        assert_account_access(user, settings)
        processor = request.app.state.processor
        await ingest(
            file,
            user,
            settings,
            db,
            processor.transcription.name == "demo" or processor.qa.name == "demo",
            item,
            lease,
            rubric_id=batch.rubric_id,
        )
    except BaseException as exc:
        db.rollback()
        db.execute(
            update(UploadItem)
            .where(UploadItem.id == item.id, UploadItem.call_id.is_(None), UploadItem.updated_at == lease)
            .values(
                status="failed",
                error=exc.detail
                if isinstance(exc, HTTPException)
                else "Upload was interrupted or storage is unavailable. Reselect the recording to retry.",
                updated_at=time.time(),
            )
        )
        db.commit()
        if not isinstance(exc, HTTPException):
            raise
    db.expire_all()
    return batch_view(get_batch(db, batch_id, user))
