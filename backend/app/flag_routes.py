from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator
from sqlalchemy import select, update
from .auth import get_db, require
from .models import FlagRule, FlagDetection, FlagNotification, Call, User, AdminEvent
from .schemas import StrictModel
from .services.flags import detect, tokens
from .services.hierarchy import lock_organization
from .services.performance import transcript_revision

router = APIRouter()


class RuleBody(StrictModel):
    phrase: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    severity: Literal["info", "attention", "urgent"] = "attention"
    notify: bool = False
    recipients: list[str] = Field(default_factory=list, max_length=10)
    revision: int = Field(default=1, ge=1)

    @field_validator("phrase")
    @classmethod
    def valid(cls, value):
        if not tokens(value):
            raise ValueError("Enter a word or phrase")
        return value.strip()


def rule_view(r):
    return {k: getattr(r, k) for k in ("id", "phrase", "enabled", "severity", "notify", "recipients", "revision")}


@router.get("/flag-rules")
def rules(user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    return {
        "items": [
            rule_view(r)
            for r in db.scalars(
                select(FlagRule).where(FlagRule.organization_id == user.organization_id).order_by(FlagRule.created_at)
            )
        ],
        "recipients": [
            {"id": u.id, "name": u.name, "email": u.email}
            for u in db.scalars(
                select(User).where(
                    User.organization_id == user.organization_id, User.active.is_(True), User.email_verified.is_(True)
                )
            )
        ],
    }


def save_rule(db, user, body, existing=None):
    lock_organization(db, user.organization_id)
    if existing and body.revision != existing.revision:
        raise HTTPException(409, "Rule changed. Reload before saving.")
    all_rules = db.scalars(select(FlagRule).where(FlagRule.organization_id == user.organization_id)).all()
    if not existing and len(all_rules) >= 100:
        raise HTTPException(422, "A maximum of 100 rules is supported.")
    normalized = [t[0] for t in tokens(body.phrase)]
    if any(
        r.id != (existing.id if existing else None) and [t[0] for t in tokens(r.phrase)] == normalized
        for r in all_rules
    ):
        raise HTTPException(409, "This phrase already has a rule. Edit the existing rule.")
    if body.notify and not body.recipients:
        raise HTTPException(422, "Select at least one organization recipient.")
    if len(set(body.recipients)) != len(body.recipients):
        raise HTTPException(422, "Recipients must be unique.")
    for uid in body.recipients:
        recipient = db.get(User, uid)
        if (
            not recipient
            or recipient.organization_id != user.organization_id
            or not recipient.active
            or not recipient.email_verified
        ):
            raise HTTPException(404, "Active verified organization recipient not found.")
    rule = existing or FlagRule(organization_id=user.organization_id, created_by=user.id)
    for key in ("phrase", "enabled", "severity", "notify", "recipients"):
        setattr(rule, key, getattr(body, key))
    rule.revision = rule.revision + 1 if existing else 1
    db.add(rule)
    db.flush()
    db.add(
        AdminEvent(
            organization_id=user.organization_id,
            actor_id=user.id,
            resource_type="flag_rule",
            resource_id=rule.id,
            action="updated" if existing else "created",
        )
    )
    db.commit()
    return rule_view(rule)


@router.post("/flag-rules", status_code=201)
def create(body: RuleBody, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    return save_rule(db, user, body)


@router.put("/flag-rules/{rule_id}")
def edit(rule_id: str, body: RuleBody, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    lock_organization(db, user.organization_id)
    rule = db.scalar(select(FlagRule).where(FlagRule.id == rule_id, FlagRule.organization_id == user.organization_id))
    if rule is None:
        raise HTTPException(404, "Rule not found")
    return save_rule(db, user, body, rule)


@router.post("/flag-rules/scan-existing")
def scan(offset: int = Query(0, ge=0), user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    calls = db.scalars(
        select(Call).where(Call.organization_id == user.organization_id).order_by(Call.id).offset(offset).limit(100)
    ).all()
    for call in calls:
        detect(db, call)
    db.commit()
    return {"scanned": len(calls), "next_offset": offset + 100 if len(calls) == 100 else None}


@router.get("/calls/{call_id}/flags")
def flags(call_id: str, history: bool = False, user=Depends(require("review")), db=Depends(get_db)):
    call = db.scalar(select(Call).where(Call.id == call_id, Call.organization_id == user.organization_id))
    if call is None:
        raise HTTPException(404, "Interaction not found")
    current = transcript_revision(db, call.id)
    query = select(FlagDetection).join(FlagRule).where(FlagDetection.call_id == call.id)
    if not history:
        query = query.where(
            FlagRule.enabled.is_(True),
            FlagDetection.rule_revision == FlagRule.revision,
            FlagDetection.transcript_revision == current,
        )
    items = db.scalars(query.order_by(FlagDetection.created_at.desc())).all()
    return {
        "transcript_revision": current,
        "items": [
            dict(
                id=d.id,
                phrase=d.phrase,
                severity=d.severity,
                matches=d.matches,
                transcript_revision=d.transcript_revision,
                rule_revision=d.rule_revision,
                created_at=d.created_at,
            )
            for d in items
            if d.matches
        ],
    }


@router.get("/flag-notifications")
def notifications(user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    rows = db.execute(
        select(FlagNotification, Call.audit_number)
        .join(FlagDetection, FlagDetection.id == FlagNotification.detection_id)
        .join(Call, Call.id == FlagDetection.call_id)
        .where(Call.organization_id == user.organization_id)
        .order_by(FlagNotification.created_at.desc())
        .limit(100)
    ).all()
    return [dict(id=n.id, audit_number=number, status=n.status, created_at=n.created_at) for n, number in rows]


@router.post("/flag-notifications/{notification_id}/retry")
def retry(notification_id: str, user=Depends(require("manage_rubrics")), db=Depends(get_db)):
    n = db.scalar(
        select(FlagNotification)
        .join(FlagDetection)
        .join(Call)
        .where(FlagNotification.id == notification_id, Call.organization_id == user.organization_id)
    )
    if n is None:
        raise HTTPException(404, "Notification not found")
    changed = db.execute(
        update(FlagNotification)
        .where(FlagNotification.id == n.id, FlagNotification.status.in_(["uncertain", "blocked"]))
        .values(status="pending")
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Only an uncertain or access-blocked delivery can be retried explicitly.")
    db.commit()
    return {"message": "Retry queued; the previous SMTP attempt may already have been accepted."}
