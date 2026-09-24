"""One tenant-scoped snapshot for the owner briefing. No transcript loads or AI metrics."""

import hashlib
import json
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ..models import Call, Employee, Evaluation, Rubric, ScoreAdjustment, SpeakerCorrection
from .reviews import evaluation_view


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def snapshot(db, organization_id):
    employees = {e.id: e for e in db.scalars(select(Employee).where(Employee.organization_id == organization_id))}
    calls = db.scalars(
        select(Call).where(Call.organization_id == organization_id).order_by(Call.created_at.desc(), Call.id)
    ).all()
    # Window selection fetches only the latest successful result, never all QA history.
    ranked = (
        select(
            Evaluation.id,
            func.row_number()
            .over(partition_by=Evaluation.call_id, order_by=(Evaluation.created_at.desc(), Evaluation.id.desc()))
            .label("position"),
        )
        .join(Call)
        .where(Call.organization_id == organization_id)
        .subquery()
    )
    evaluations = db.scalars(
        select(Evaluation)
        .join(ranked, Evaluation.id == ranked.c.id)
        .where(ranked.c.position == 1)
        .options(
            selectinload(Evaluation.rubric).selectinload(Rubric.categories),
            selectinload(Evaluation.adjustments).selectinload(ScoreAdjustment.actor),
        )
    ).all()
    revisions = dict(
        db.execute(
            select(SpeakerCorrection.call_id, func.max(SpeakerCorrection.id))
            .join(Call)
            .where(Call.organization_id == organization_id)
            .group_by(SpeakerCorrection.call_id)
        ).all()
    )
    views = {e.call_id: evaluation_view(e) for e in evaluations}
    issues, rows, scores = {}, [], []
    team_scores = defaultdict(list)
    team_calls = defaultdict(int)
    for call in calls:
        qa = views.get(call.id)
        stale = bool(qa and qa["transcript_revision"] != revisions.get(call.id, 0))
        person = employees.get(call.employee_id)
        manager = employees.get(person.manager_id) if person else None
        eligible = qa is not None and not stale
        score = qa["final_score"] if eligible else None
        row = dict(
            id=call.id,
            filename=call.filename,
            status=call.status,
            employee_id=person.id if person else None,
            employee_name=person.name if person else None,
            manager_id=manager.id if manager else None,
            manager_name=manager.name if manager else None,
            score=score,
            stale=stale,
            is_demo=call.is_demo,
            rubric_name=qa["rubric_name"] if qa else None,
            rubric_version=qa["rubric_version"] if qa else None,
            needs_review=bool(qa and (stale or not qa["reviewed_at"])),
        )
        rows.append(row)
        if manager:
            team_calls[manager.id] += 1
        if not eligible:
            continue
        scores.append(score)
        if manager:
            team_scores[manager.id].append(score)
        for c in qa["categories"]:
            requirement = next((r for r in qa["rubric"] if r["key"] == c["key"]), None)
            # Legacy results without an immutable requirement cannot ground communications.
            if requirement is None:
                continue
            key = digest([organization_id, qa["rubric_id"], qa["rubric_version"], c["key"], c["max_score"]])
            issue = issues.setdefault(
                key,
                dict(
                    id=key,
                    rubric_id=qa["rubric_id"],
                    rubric_name=qa["rubric_name"],
                    rubric_version=qa["rubric_version"],
                    category_key=c["key"],
                    name=requirement["label"],
                    criteria=requirement["criteria"],
                    description=requirement.get("description", ""),
                    max_score=c["max_score"],
                    eligible=0,
                    occurrences=0,
                    employees=set(),
                    evidence=[],
                    population=[],
                ),
            )
            issue["eligible"] += 1
            issue["population"].append(
                [
                    call.id,
                    qa["id"],
                    qa["revision"],
                    person.id if person else None,
                    manager.id if manager else None,
                    c["final_score"],
                    call.is_demo,
                ]
            )
            if c["final_score"] < c["max_score"]:
                issue["occurrences"] += 1
                if person:
                    issue["employees"].add(person.id)
                issue["evidence"].append(
                    {
                        **row,
                        "evaluation_id": qa["id"],
                        "category_score": c["final_score"],
                        "original_score": c["score"],
                        "overridden": c["overridden"],
                        "explanation": c["explanation"],
                        "quotes": c["evidence"],
                    }
                )
    result = []
    for issue in issues.values():
        if not issue["occurrences"]:
            continue
        issue["affected_employees"] = len(issue.pop("employees"))
        issue["unassigned"] = sum(e["employee_id"] is None for e in issue["evidence"])
        issue["percent"] = round(100 * issue["occurrences"] / issue["eligible"], 1)
        issue["limited_sample"] = issue["eligible"] < 5
        issue["coaching_ready"] = issue["eligible"] >= 5 and issue["occurrences"] >= 2
        issue["fingerprint"] = digest(
            [issue["id"], sorted(issue.pop("population")), issue["criteria"], issue["description"]]
        )
        result.append(issue)
    result.sort(key=lambda i: (-i["occurrences"], i["id"]))
    teams = []
    report_counts = defaultdict(int)
    for person in employees.values():
        report_counts[person.manager_id] += 1
    for manager in sorted(employees.values(), key=lambda e: (e.name.casefold(), e.id)):
        if not manager.manager_eligible:
            continue
        values = team_scores[manager.id]
        teams.append(
            dict(
                id=manager.id,
                name=manager.name,
                active=manager.active,
                direct_reports=report_counts[manager.id],
                interactions=team_calls[manager.id],
                analyzed=len(values),
                limited_sample=len(values) < 5,
                score=round(sum(values) / len(values), 1) if values else None,
            )
        )
    return dict(
        signal_score=round(sum(scores) / len(scores), 1) if scores else None,
        analyzed=len(scores),
        limited_sample=len(scores) < 5,
        total=len(calls),
        active_employees=sum(e.active for e in employees.values()),
        needs_attention=sum(r["needs_review"] or r["status"] == "failed" for r in rows),
        requiring_review=sum(r["needs_review"] for r in rows),
        stale=sum(r["stale"] for r in rows),
        failed=sum(r["status"] == "failed" for r in rows),
        awaiting=sum(r["status"] in {"queued", "transcribing", "analyzing"} for r in rows),
        period="All time · current assignments",
        issues=result,
        teams=teams,
        recent=rows[:8],
    )


def public_summary(value):
    return {
        **value,
        "issues": [{k: v for k, v in i.items() if k not in {"evidence", "fingerprint"}} for i in value["issues"]],
    }
