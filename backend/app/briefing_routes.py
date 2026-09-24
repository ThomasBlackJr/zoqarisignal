import time
from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from .auth import get_db, require, PERMISSIONS
from .logging import event
from .models import CoachingDraft
from .schemas import StrictModel
from .services.briefing import snapshot, public_summary
from .services.coaching import CoachingChoice, grounding, materialize
from .services.entitlements import assert_account_access

router = APIRouter()


def find_issue(db, org, issue_id):
    issue = next((i for i in snapshot(db, org)["issues"] if i["id"] == issue_id), None)
    if issue is None:
        raise HTTPException(404, "Current quality issue not found. Refresh the dashboard.")
    return issue


def cached(db, org, issue):
    value = db.get(CoachingDraft, (org, issue["id"]))
    return (
        materialize(issue, value.choice, value.provider, value.created_at)
        if value and value.fingerprint == issue["fingerprint"]
        else None
    )


@router.get("/briefing")
def briefing(user=Depends(require("review")), db=Depends(get_db)):
    value = snapshot(db, user.organization_id)
    saved = {
        d.issue_id: d
        for d in db.scalars(select(CoachingDraft).where(CoachingDraft.organization_id == user.organization_id))
    }
    for issue in value["issues"]:
        draft = saved.get(issue["id"])
        issue["recommendation"] = None
        issue["recommendation_synthetic"] = False
        if issue["coaching_ready"] and draft and draft.fingerprint == issue["fingerprint"]:
            issue["recommendation"] = materialize(issue, draft.choice, draft.provider, draft.created_at)[
                "recommendation"
            ]
            issue["recommendation_synthetic"] = draft.provider == "demo"
    return public_summary(value)


@router.get("/briefing/issues/{issue_id}")
def details(issue_id: str, offset: int = Query(0, ge=0), user=Depends(require("review")), db=Depends(get_db)):
    issue = find_issue(db, user.organization_id, issue_id)
    return {
        **issue,
        "evidence": issue["evidence"][offset : offset + 25],
        "offset": offset,
        "draft": cached(db, user.organization_id, issue) if issue["coaching_ready"] else None,
    }


class Generate(StrictModel):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    regenerate: bool = False


@router.post("/briefing/issues/{issue_id}/generate")
def generate(issue_id: str, body: Generate, request: Request, user=Depends(require("review")), db=Depends(get_db)):
    if not request.app.state.coaching_lock.acquire(blocking=False):
        raise HTTPException(409, "A draft is being prepared. Please try again shortly.")
    try:
        issue = find_issue(db, user.organization_id, issue_id)
        if body.fingerprint != issue["fingerprint"]:
            raise HTTPException(409, "Evidence changed. Reopen this issue before generating.")
        if not issue["coaching_ready"]:
            raise HTTPException(409, "Coaching requires five eligible interactions and at least two occurrences.")
        saved = cached(db, user.organization_id, issue)
        if saved and not body.regenerate:
            return saved
        context = grounding(issue)
        if len(str(context)) > 18000:
            raise HTTPException(422, "Scorecard context is too long for bounded coaching generation.")
        provider = request.app.state.coaching
        try:
            choice = CoachingChoice.model_validate(provider.recommend(context)).model_dump()
        except Exception as exc:
            event("coaching_failed", reason="provider_or_contract", error_type=type(exc).__name__)
            raise HTTPException(
                502, "Draft generation failed validation or provider delivery. No draft was saved."
            ) from None
        # End the read transaction and recheck the current evidence/access after a slow paid request.
        db.rollback()
        db.refresh(user)
        assert_account_access(user, request.app.state.settings)
        if not user.active or "review" not in PERMISSIONS.get(user.role, set()):
            raise HTTPException(403, "Your role no longer permits this action.")
        fresh = find_issue(db, user.organization_id, issue_id)
        if fresh["fingerprint"] != issue["fingerprint"]:
            raise HTTPException(409, "Evidence changed during generation. Reopen the issue; no draft was saved.")
        value = db.get(CoachingDraft, (user.organization_id, issue_id))
        if value is None:
            value = CoachingDraft(organization_id=user.organization_id, issue_id=issue_id)
            db.add(value)
        value.fingerprint, value.choice = issue["fingerprint"], choice
        value.provider, value.model, value.created_at = provider.name, provider.model, time.time()
        db.commit()
        return materialize(issue, choice, value.provider, value.created_at)
    finally:
        request.app.state.coaching_lock.release()
