"""Single definition of current performance; historical/stale results never inflate aggregates."""

from collections import defaultdict
from sqlalchemy import select, func
from ..models import SpeakerCorrection
from .reviews import evaluation_view, corrected_conversation


def transcript_revision(db, call_id):
    return db.scalar(select(func.max(SpeakerCorrection.id)).where(SpeakerCorrection.call_id == call_id)) or 0


def snapshot_context(db, transcript):
    view = corrected_conversation(transcript, db)
    return {
        "revision": view["revision"],
        "source_fingerprint": view["source_fingerprint"],
        "turns": [
            {
                "source_start": t["source_start"],
                "source_end": t["source_end"],
                "role": t["effective_role"],
                "manual": t["manual_role"] is not None,
            }
            for t in view["turns"]
        ],
    }


def evaluated_view(call, db):
    if not call.evaluation:
        return None
    return evaluation_context_view(call.evaluation, db)


def evaluation_context_view(evaluation, db):
    value = evaluation_view(evaluation)
    value["current_transcript_revision"] = transcript_revision(db, evaluation.call_id)
    value["stale"] = evaluation.transcript_revision != value["current_transcript_revision"]
    return value


def current_performance(calls, db):
    scores = []
    categories = defaultdict(list)
    labels = {}
    rubrics = {}
    strengths = []
    coaching = []
    stale = 0
    for call in calls:
        qa = evaluated_view(call, db)
        if not qa:
            continue
        if qa["stale"]:
            stale += 1
            continue
        scores.append(qa["final_score"])
        for category in qa["categories"]:
            key = (qa["rubric_id"], category["key"], category["max_score"])
            rubrics[key] = (qa["rubric_name"], qa["rubric_version"])
            labels[key] = next((c["label"] for c in qa["rubric"] if c["key"] == category["key"]), category["key"])
            categories[key].append(category["final_score"])
        strengths.extend({"call_id": call.id, "text": value} for value in qa["strengths"])
        coaching.extend({"call_id": call.id, "text": value} for value in qa["coaching_opportunities"])
    return {
        "interactions": len(calls),
        "analyzed": len(scores),
        "stale": stale,
        "signal_score": round(sum(scores) / len(scores), 1) if scores else None,
        "limited_sample": len(scores) < 5,
        "categories": [
            {
                "rubric_id": k[0],
                "rubric_name": rubrics[k][0],
                "rubric_version": rubrics[k][1],
                "key": k[1],
                "name": labels[k],
                "max_score": k[2],
                "average": round(sum(v) / len(v), 2),
                "sample_count": len(v),
            }
            for k, v in categories.items()
        ],
        "strengths": strengths[:10],
        "coaching_opportunities": coaching[:10],
    }
