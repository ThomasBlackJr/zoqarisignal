"""Call intelligence uses the existing review/admin and entitlement boundary."""

import re
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, func, or_, and_
from .auth import require, get_db
from .models import Call, CallAttribute, AttributeEvent, Organization, AdminEvent, RelatedExclusion
from .schemas import StrictModel
from .review_routes import lock_call
from .services.company_context import Vocabulary, vocabulary
from .services.call_attributes import FIELDS, IDENTIFIERS, normalize, attribute_view, sync_attributes

router = APIRouter()


def owned(db, call_id, user):
    call = db.scalar(select(Call).where(Call.id == call_id, Call.organization_id == user.organization_id))
    if call is None:
        raise HTTPException(404, "Interaction not found")
    return call


def rows(db, call):
    return db.scalars(
        select(CallAttribute).where(
            CallAttribute.call_id == call.id, CallAttribute.organization_id == call.organization_id
        )
    ).all()


class AttributeEdit(StrictModel):
    value: str | None = Field(default=None, max_length=500)
    verified: bool = True
    revision: int = Field(ge=0)


@router.get("/organization/transcription-vocabulary")
def get_vocabulary(user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    return vocabulary(db.get(Organization, user.organization_id))


@router.put("/organization/transcription-vocabulary")
def put_vocabulary(body: Vocabulary, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    from .services.hierarchy import lock_organization

    lock_organization(db, user.organization_id)
    organization = db.get(Organization, user.organization_id)
    organization.transcription_vocabulary = body.model_dump()
    db.add(
        AdminEvent(
            organization_id=user.organization_id,
            actor_id=user.id,
            resource_type="organization",
            resource_id=user.organization_id,
            action="transcription_vocabulary_updated",
        )
    )
    db.commit()
    return vocabulary(organization)


@router.get("/calls/{call_id}/intelligence")
def intelligence(call_id: str, user=Depends(require("review")), db=Depends(get_db)):
    call = owned(db, call_id, user)
    stored = {r.key: r for r in rows(db, call)}
    return {
        "attributes": [
            dict(attribute_view(stored[key]), label=label)
            if key in stored
            else {"key": key, "label": label, "value": None, "revision": 0, "verified": False, "origin": "unprocessed"}
            for key, label in FIELDS.items()
        ],
        "processed": bool(stored),
    }


@router.post("/calls/{call_id}/intelligence/refresh")
def refresh(call_id: str, user=Depends(require("review")), db=Depends(get_db)):
    call = lock_call(db, call_id, user)
    if call.transcript is None:
        raise HTTPException(409, "Transcript is not available")
    sync_attributes(db, call)
    db.commit()
    return intelligence(call_id, user, db)


@router.put("/calls/{call_id}/attributes/{key}")
def edit_attribute(call_id: str, key: str, body: AttributeEdit, user=Depends(require("review")), db=Depends(get_db)):
    if key not in FIELDS:
        raise HTTPException(422, "Unsupported attribute")
    call = lock_call(db, call_id, user)
    if call.transcript is None:
        raise HTTPException(409, "Transcript is not available")
    row = next((r for r in rows(db, call) if r.key == key), None)
    if (row.revision if row else 0) != body.revision:
        raise HTTPException(409, "Attribute changed. Reload before saving.")
    value = body.value.strip() if body.value else None
    if value == "":
        value = None
    if (
        value
        and key in IDENTIFIERS
        and (not re.fullmatch(r"[A-Za-z0-9 -]{3,64}", value) or not any(c.isdigit() for c in value))
    ):
        raise HTTPException(422, "Use a complete identifier with letters, digits, spaces or hyphens")
    before = attribute_view(row) if row else None
    if row is None:
        row = CallAttribute(organization_id=user.organization_id, call_id=call.id, key=key, revision=0)
        db.add(row)
    if row.value != value:
        for name in ("source_start", "source_end", "source_segment", "timestamp", "confidence"):
            setattr(row, name, None)
    row.value = value
    row.normalized_value = normalize(key, value) if value else None
    row.origin = "manual"
    row.verified = bool(value and body.verified)
    row.revision += 1
    row.updated_at = time.time()
    db.flush()
    db.add(
        AttributeEvent(
            organization_id=user.organization_id,
            call_id=call.id,
            key=key,
            actor_id=user.id,
            previous=before,
            current=attribute_view(row),
        )
    )
    db.commit()
    return dict(attribute_view(row), label=FIELDS[key])


@router.get("/calls/{call_id}/attributes/history")
def history(
    call_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    user=Depends(require("review")),
    db=Depends(get_db),
):
    owned(db, call_id, user)
    query = select(AttributeEvent).where(
        AttributeEvent.call_id == call_id, AttributeEvent.organization_id == user.organization_id
    )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {
        "total": total,
        "items": [
            {
                "id": e.id,
                "key": e.key,
                "actor_id": e.actor_id,
                "previous": e.previous,
                "current": e.current,
                "created_at": e.created_at,
            }
            for e in db.scalars(query.order_by(AttributeEvent.id.desc()).offset(offset).limit(limit))
        ],
    }


def matching(query, key):
    if key in IDENTIFIERS:
        return CallAttribute.normalized_value == normalize(key, query)
    if key:
        return CallAttribute.normalized_value.icontains(normalize(key, query), autoescape=True)
    return or_(
        and_(CallAttribute.key.in_(IDENTIFIERS), CallAttribute.normalized_value == normalize("order", query)),
        and_(
            CallAttribute.key.not_in(IDENTIFIERS),
            CallAttribute.normalized_value.icontains(normalize("customer", query), autoescape=True),
        ),
    )


@router.get("/intelligence/search")
def search(
    q: str = Query(min_length=1, max_length=200),
    key: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require("review")),
    db=Depends(get_db),
):
    key = key or None
    if key is not None and key not in FIELDS:
        raise HTTPException(422, "Unsupported attribute")
    if not q.strip():
        return {"items": [], "total": 0}
    attributes = select(CallAttribute.call_id).where(
        CallAttribute.organization_id == user.organization_id, CallAttribute.value.is_not(None), matching(q, key)
    )
    if key:
        attributes = attributes.where(CallAttribute.key == key)
    query = select(Call).where(Call.organization_id == user.organization_id, Call.id.in_(attributes))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = []
    from .main import call_view

    for call in db.scalars(query.order_by(Call.created_at.desc(), Call.id).offset(offset).limit(limit)):
        record = call_view(call, db=db)
        record["customer"] = next((r.value for r in rows(db, call) if r.key == "customer"), None)
        record["matches"] = [
            dict(attribute_view(r), label=FIELDS.get(r.key, r.key))
            for r in db.scalars(
                select(CallAttribute).where(
                    CallAttribute.call_id == call.id,
                    CallAttribute.organization_id == user.organization_id,
                    matching(q, key),
                    CallAttribute.value.is_not(None),
                    *([CallAttribute.key == key] if key else []),
                )
            )
        ]
        items.append(record)
    return {"items": items, "total": total}


@router.get("/calls/{call_id}/related")
def related(
    call_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require("review")),
    db=Depends(get_db),
):
    call = owned(db, call_id, user)
    source = [r for r in rows(db, call) if r.key in IDENTIFIERS and r.verified and r.normalized_value]
    if not source:
        return {"items": [], "total": 0}
    matches = select(CallAttribute.call_id).where(
        CallAttribute.organization_id == user.organization_id,
        CallAttribute.verified.is_(True),
        CallAttribute.value.is_not(None),
        or_(*[and_(CallAttribute.key == r.key, CallAttribute.normalized_value == r.normalized_value) for r in source]),
    )
    exclusion = (
        select(RelatedExclusion.id)
        .where(
            RelatedExclusion.organization_id == user.organization_id,
            or_(
                and_(RelatedExclusion.left_call_id == call.id, RelatedExclusion.right_call_id == Call.id),
                and_(RelatedExclusion.right_call_id == call.id, RelatedExclusion.left_call_id == Call.id),
            ),
        )
        .exists()
    )
    query = select(Call).where(
        Call.organization_id == user.organization_id, Call.id != call.id, Call.id.in_(matches), ~exclusion
    )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    from .main import call_view

    items = []
    for candidate in db.scalars(query.order_by(Call.created_at.desc(), Call.id).offset(offset).limit(limit)):
        record = call_view(candidate, db=db)
        attrs = rows(db, candidate)
        record["customer"] = next((r.value for r in attrs if r.key == "customer"), None)
        record["matches"] = [
            {"key": r.key, "label": FIELDS[r.key], "value": r.value}
            for r in attrs
            if r.verified and any(r.key == s.key and r.normalized_value == s.normalized_value for s in source)
        ]
        items.append(record)
    return {"items": items, "total": total}


@router.post("/calls/{call_id}/related/{other_id}/exclude")
def exclude_related(call_id: str, other_id: str, user=Depends(require("review")), db=Depends(get_db)):
    from .services.hierarchy import lock_organization

    lock_organization(db, user.organization_id)
    owned(db, call_id, user)
    owned(db, other_id, user)
    if call_id == other_id:
        raise HTTPException(422, "Choose a different interaction")
    left, right = sorted([call_id, other_id])
    existing = db.scalar(
        select(RelatedExclusion).where(
            RelatedExclusion.organization_id == user.organization_id,
            RelatedExclusion.left_call_id == left,
            RelatedExclusion.right_call_id == right,
        )
    )
    if existing is None:
        db.add(
            RelatedExclusion(
                organization_id=user.organization_id, left_call_id=left, right_call_id=right, actor_id=user.id
            )
        )
        db.commit()
    return {"excluded": True}
