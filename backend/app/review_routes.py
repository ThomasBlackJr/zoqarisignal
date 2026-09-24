"""Authenticated supervisor commands and versioned rubric management."""

import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from .auth import get_db, require
from .models import Call, Evaluation, Rubric, RubricCategory, SpeakerCorrection, ScoreAdjustment, Status, identifier
from .review_schemas import RubricDraft, Revision, SpeakerEdit, ScoreEdit, Reevaluation
from .services.rubric import selected_rubric
from .services.reviews import rubric_view, evaluation_view, corrected_conversation
from .services.performance import snapshot_context, evaluation_context_view

router = APIRouter()


def get_rubric(db, rubric_id, user):
    value = db.scalar(select(Rubric).where(Rubric.id == rubric_id, Rubric.organization_id == user.organization_id))
    if value is None:
        raise HTTPException(404, "Rubric not found")
    return value


def lock_call(db, call_id, user):
    # A write lock serializes audit projection + insertion on SQLite and PostgreSQL.
    found = db.execute(
        update(Call).where(Call.id == call_id, Call.organization_id == user.organization_id).values(id=Call.id)
    )
    if found.rowcount != 1:
        raise HTTPException(404, "Call not found")
    db.expire_all()
    return db.get(Call, call_id)


def assign_categories(rubric, categories):
    allowed = {c.key for c in rubric.categories}
    seen = set()
    result = []
    for i, c in enumerate(categories):
        key = c.key or "c_" + identifier().replace("-", "")
        if c.key is not None and key not in allowed:
            raise HTTPException(422, "Unknown category key; omit the key for a new category")
        if key in seen:
            raise HTTPException(422, "Duplicate category")
        seen.add(key)
        result.append(
            RubricCategory(
                key=key, name=c.name, description=c.description, weight=c.weight, criteria=c.criteria, display_order=i
            )
        )
    rubric.categories = result


def next_version(db, organization_id):
    return (
        f"{db.scalar(select(func.count()).select_from(Rubric).where(Rubric.organization_id == organization_id)) + 1}.0"
    )


@router.get("/rubrics")
def list_rubrics(user=Depends(require("review")), db=Depends(get_db)):
    return [
        rubric_view(r)
        for r in db.scalars(
            select(Rubric).where(Rubric.organization_id == user.organization_id).order_by(Rubric.created_at.desc())
        ).all()
    ]


@router.post("/rubrics", status_code=201)
def create_rubric(body: RubricDraft, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    rubric = Rubric(
        name=body.name,
        version=next_version(db, user.organization_id),
        created_by=user.id,
        organization_id=user.organization_id,
    )
    assign_categories(rubric, body.categories)
    db.add(rubric)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Another draft was created. Reload and try again.") from exc
    return rubric_view(rubric)


@router.post("/rubrics/{rubric_id}/duplicate", status_code=201)
def duplicate(rubric_id: str, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    source = get_rubric(db, rubric_id, user)
    value = Rubric(
        name=source.name,
        version=next_version(db, user.organization_id),
        created_by=user.id,
        organization_id=user.organization_id,
    )
    value.categories = [
        RubricCategory(
            key=c.key,
            name=c.name,
            description=c.description,
            weight=c.weight,
            criteria=c.criteria,
            display_order=c.display_order,
        )
        for c in source.categories
    ]
    db.add(value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Another draft was created. Reload and try again.") from exc
    return rubric_view(value)


@router.put("/rubrics/{rubric_id}")
def edit_rubric(rubric_id: str, body: RubricDraft, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    changed = db.execute(
        update(Rubric)
        .where(
            Rubric.id == rubric_id,
            Rubric.organization_id == user.organization_id,
            Rubric.status == "DRAFT",
            Rubric.revision == body.revision,
        )
        .values(revision=Rubric.revision + 1)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Only the current draft can be edited. Reload this rubric.")
    value = get_rubric(db, rubric_id, user)
    value.name = body.name
    assign_categories(value, body.categories)
    db.commit()
    return rubric_view(value)


@router.post("/rubrics/{rubric_id}/activate")
def activate(rubric_id: str, body: Revision, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    changed = db.execute(
        update(Rubric)
        .where(
            Rubric.id == rubric_id,
            Rubric.organization_id == user.organization_id,
            Rubric.status == "DRAFT",
            Rubric.revision == body.revision,
        )
        .values(revision=Rubric.revision + 1)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Only the current draft can be published. Reload this rubric.")
    value = get_rubric(db, rubric_id, user)
    if not value.categories or sum(c.weight for c in value.categories) != 100:
        raise HTTPException(422, "Category weights must total exactly 100 before publication")
    value.status = "ACTIVE"
    value.activated_at = time.time()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Another rubric was published. Reload and try again.") from exc
    return rubric_view(value)


@router.post("/rubrics/{rubric_id}/archive")
def archive(rubric_id: str, body: Revision, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    changed = db.execute(
        update(Rubric)
        .where(
            Rubric.id == rubric_id,
            Rubric.organization_id == user.organization_id,
            Rubric.revision == body.revision,
        )
        .values(status="ARCHIVED", revision=Rubric.revision + 1)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Scorecard changed. Reload before archiving.")
    db.commit()
    return rubric_view(get_rubric(db, rubric_id, user))


@router.post("/calls/{call_id}/speakers")
def correct_speaker(call_id: str, body: SpeakerEdit, user=Depends(require("review")), db=Depends(get_db)):
    call = lock_call(db, call_id, user)
    if call.transcript is None:
        raise HTTPException(409, "Transcript is not available yet")
    conversation = corrected_conversation(call.transcript, db)
    if conversation["source_fingerprint"] != body.source_fingerprint or conversation["revision"] != body.revision:
        raise HTTPException(409, "The transcript view changed. Reload before correcting a speaker.")
    turn = next(
        (
            t
            for t in conversation["turns"]
            if t["source_start"] == body.source_start and t["source_end"] == body.source_end
        ),
        None,
    )
    if turn is None:
        raise HTTPException(422, "Select an existing conversational turn")
    if body.scope == "speaker" and turn["speaker_id"] is None:
        raise HTTPException(422, "Bulk correction requires a detected speaker ID")
    targets = (
        [t for t in conversation["turns"] if t["speaker_id"] == turn["speaker_id"]]
        if body.scope == "speaker"
        else [turn]
    )
    for t in targets:
        db.add(
            SpeakerCorrection(
                call_id=call_id,
                source_fingerprint=body.source_fingerprint,
                source_start=t["source_start"],
                source_end=t["source_end"],
                speaker_id=t["speaker_id"],
                inferred_role=t["inferred_role"],
                previous_role=t["effective_role"],
                corrected_role=body.role,
                scope=body.scope,
                corrected_by=user.id,
            )
        )
    db.commit()
    from .services.flags import detect

    detect(db, call)
    db.commit()
    return corrected_conversation(call.transcript, db)


def current_evaluation(db, call_id, evaluation_id, user):
    call = lock_call(db, call_id, user)
    if call.status not in (Status.COMPLETED, Status.FAILED):
        raise HTTPException(409, "Wait for processing to finish")
    if call.evaluation is None or call.evaluation.id != evaluation_id:
        raise HTTPException(409, "Select the latest evaluation; historical evaluations are read-only")
    return call.evaluation


@router.post("/calls/{call_id}/evaluations/{evaluation_id}/categories/{key}")
def adjust_score(
    call_id: str, evaluation_id: str, key: str, body: ScoreEdit, user=Depends(require("review")), db=Depends(get_db)
):
    evaluation = current_evaluation(db, call_id, evaluation_id, user)
    view = evaluation_view(evaluation)
    if body.revision != view["revision"]:
        raise HTTPException(409, "Another supervisor changed this evaluation. Reload before saving.")
    category = next((c for c in view["categories"] if c["key"] == key), None)
    if category is None or (body.score is not None and body.score > category["max_score"]):
        raise HTTPException(422, "Score must be within the evaluated category bounds")
    db.add(
        ScoreAdjustment(
            evaluation_id=evaluation.id,
            category_key=key,
            score=body.score,
            previous_score=category["final_score"],
            reason=body.reason,
            changed_by=user.id,
        )
    )
    evaluation.reviewed_at = None
    evaluation.reviewed_by = None
    db.commit()
    db.expire(evaluation, ["adjustments"])
    return evaluation_view(evaluation)


@router.post("/calls/{call_id}/evaluations/{evaluation_id}/review")
def complete_review(
    call_id: str, evaluation_id: str, body: Revision, user=Depends(require("review")), db=Depends(get_db)
):
    evaluation = current_evaluation(db, call_id, evaluation_id, user)
    if body.revision != evaluation_view(evaluation)["revision"] + 1:
        raise HTTPException(409, "Evaluation changed. Reload before completing review.")
    evaluation.reviewed_at = time.time()
    evaluation.reviewed_by = user.id
    db.commit()
    return evaluation_view(evaluation)


@router.post("/calls/{call_id}/reevaluate")
def reevaluate(call_id: str, body: Reevaluation, user=Depends(require("review")), db=Depends(get_db)):
    call = lock_call(db, call_id, user)
    if call.status != Status.COMPLETED or not call.transcript or not call.evaluation:
        raise HTTPException(409, "Only a completed call with a saved transcript can be evaluated again")
    if call.evaluation.id != body.evaluation_id:
        raise HTTPException(409, "Evaluation changed. Reload before requesting another evaluation.")
    if body.use_previous_scorecard:
        if body.rubric_id != call.evaluation.rubric_id:
            raise HTTPException(409, "Corrected evaluation must use the previous scorecard.")
        rubric = get_rubric(db, body.rubric_id, user)
        if rubric.activated_at is None:
            raise HTTPException(409, "The prior scorecard was never published.")
    else:
        rubric = selected_rubric(db, user.organization_id, body.rubric_id)
    context = snapshot_context(db, call.transcript)
    if body.transcript_revision is not None and body.transcript_revision != context["revision"]:
        raise HTTPException(409, "Speaker corrections changed. Reload before re-evaluating.")
    call.requested_rubric_id = rubric.id
    call.requested_transcript_context = context
    call.status = Status.QUEUED
    db.commit()
    return {"status": "queued"}


@router.get("/calls/{call_id}/evaluations")
def history(call_id: str, user=Depends(require("review")), db=Depends(get_db)):
    if db.scalar(select(Call).where(Call.id == call_id, Call.organization_id == user.organization_id)) is None:
        raise HTTPException(404, "Call not found")
    return [
        evaluation_context_view(e, db)
        for e in db.scalars(
            select(Evaluation).where(Evaluation.call_id == call_id).order_by(Evaluation.created_at.desc())
        ).all()
    ]
