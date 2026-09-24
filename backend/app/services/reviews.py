"""Derived views and append-only audit projection; originals are never updated."""

from sqlalchemy import select
from ..models import SpeakerCorrection
from .conversations import conversation_for
from .rubric import rubric_items


def rubric_view(rubric):
    return dict(
        id=rubric.id,
        name=rubric.name,
        version=rubric.version,
        status=rubric.status,
        revision=rubric.revision,
        created_at=rubric.created_at,
        created_by=rubric.created_by,
        activated_at=rubric.activated_at,
        total_weight=sum(c.weight for c in rubric.categories),
        categories=[
            dict(
                id=c.id,
                key=c.key,
                name=c.name,
                description=c.description,
                weight=c.weight,
                criteria=c.criteria,
                display_order=c.display_order,
            )
            for c in rubric.categories
        ],
    )


def evaluation_view(evaluation):
    latest = {a.category_key: a for a in evaluation.adjustments}
    categories = []
    for c in evaluation.result["categories"]:
        adjustment = latest.get(c["key"])
        manual = adjustment is not None and adjustment.score is not None
        categories.append({**c, "final_score": adjustment.score if manual else c["score"], "overridden": manual})
    return {
        **evaluation.result,
        "id": evaluation.id,
        "transcript_revision": evaluation.transcript_revision,
        "transcript_context": evaluation.transcript_context,
        "categories": categories,
        "final_score": sum(c["final_score"] for c in categories),
        "has_overrides": any(c["overridden"] for c in categories),
        "revision": evaluation.adjustments[-1].id if evaluation.adjustments else 0,
        "reviewed_at": evaluation.reviewed_at,
        "reviewed_by": evaluation.reviewed_by,
        "rubric_id": evaluation.rubric_id,
        "rubric_version": evaluation.rubric_version,
        "rubric_name": evaluation.rubric.name if evaluation.rubric else "Legacy rubric",
        "rubric": rubric_items(evaluation.rubric) if evaluation.rubric else [],
        "provider": evaluation.provider,
        "model": evaluation.model,
        "created_at": evaluation.created_at,
        "adjustments": [
            dict(
                id=a.id,
                category_key=a.category_key,
                score=a.score,
                previous_score=a.previous_score,
                reason=a.reason,
                changed_by=a.changed_by,
                actor_name=a.actor.name,
                changed_at=a.changed_at,
            )
            for a in evaluation.adjustments
        ],
    }


def corrected_conversation(transcript, db):
    value = conversation_for(transcript)
    history = db.scalars(
        select(SpeakerCorrection).where(SpeakerCorrection.call_id == transcript.call_id).order_by(SpeakerCorrection.id)
    ).all()
    value["revision"] = history[-1].id if history else 0
    latest = {(a.source_start, a.source_end): a for a in history if a.source_fingerprint == value["source_fingerprint"]}
    for turn in value["turns"]:
        change = latest.get((turn["source_start"], turn["source_end"]))
        turn["inferred_role"] = turn["speaker_role"]
        turn["manual_role"] = change.corrected_role if change else None
        turn["effective_role"] = turn["manual_role"] or turn["inferred_role"]
        turn["corrected_by"] = change.corrected_by if change else None
        turn["corrected_at"] = change.corrected_at if change else None
        turn["corrector_name"] = change.actor.name if change else None
    value["history"] = [
        dict(
            id=a.id,
            source_start=a.source_start,
            source_end=a.source_end,
            inferred_role=a.inferred_role,
            previous_role=a.previous_role,
            corrected_role=a.corrected_role,
            scope=a.scope,
            corrected_by=a.corrected_by,
            corrected_at=a.corrected_at,
            actor_name=a.actor.name,
        )
        for a in history
    ]
    return value
