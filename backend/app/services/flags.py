"""Deterministic Unicode word/phrase matches with immutable revision snapshots."""

import re
import time
from sqlalchemy import select, update, func
from ..models import AuditSequence, Call, FlagRule, FlagDetection, FlagNotification, User, SpeakerCorrection
from ..logging import event
from .reviews import corrected_conversation
from .entitlements import operational_access


def tokens(text):
    return [(m.group().casefold(), m.start(), m.end()) for m in re.finditer(r"[^\W_]+", text, re.UNICODE)]


def matches(text, phrase):
    source, target = tokens(text), [w[0] for w in tokens(phrase)]
    if not target:
        return []
    n = len(target)
    return [
        (source[i][1], source[i + n - 1][2])
        for i in range(len(source) - n + 1)
        if [w[0] for w in source[i : i + n]] == target
    ]


def audit_reference(db, call):
    if not call.audit_number:
        value = AuditSequence()
        db.add(value)
        db.flush()
        call.audit_number = f"SIG-{value.id:08d}"


def current_flag_query():
    revision = (
        select(func.coalesce(func.max(SpeakerCorrection.id), 0))
        .where(SpeakerCorrection.call_id == Call.id)
        .correlate(Call)
        .scalar_subquery()
    )
    return (
        select(FlagDetection.id)
        .join(FlagRule)
        .where(
            FlagDetection.call_id == Call.id,
            FlagDetection.match_count > 0,
            FlagRule.enabled.is_(True),
            FlagDetection.rule_revision == FlagRule.revision,
            FlagDetection.transcript_revision == revision,
        )
        .correlate(Call)
    )


def detect(db, call):
    if call.transcript is None:
        return
    # All detection callers serialize on this call before checking unique snapshots.
    db.execute(update(Call).where(Call.id == call.id).values(id=Call.id))
    view = corrected_conversation(call.transcript, db)
    rules = db.scalars(
        select(FlagRule).where(FlagRule.organization_id == call.organization_id, FlagRule.enabled.is_(True))
    ).all()
    for rule in rules:
        prior = db.scalars(
            select(FlagDetection).where(FlagDetection.call_id == call.id, FlagDetection.rule_id == rule.id)
        ).all()
        if any(p.rule_revision == rule.revision and p.transcript_revision == view["revision"] for p in prior):
            continue
        found = []
        for start, end in matches(call.transcript.text, rule.phrase):
            turn = next((t for t in view["turns"] if t["source_start"] <= start < t["source_end"]), None)
            found.append(
                dict(
                    source_start=start,
                    source_end=end,
                    quote=call.transcript.text[max(0, start - 60) : min(len(call.transcript.text), end + 60)],
                    role=turn["effective_role"] if turn else "UNKNOWN",
                    start=turn.get("start") if turn else None,
                    end=turn.get("end") if turn else None,
                )
            )
        # Empty snapshots record that a scan happened but are never counted as flags.
        detection = FlagDetection(
            call_id=call.id,
            rule_id=rule.id,
            rule_revision=rule.revision,
            transcript_revision=view["revision"],
            source_fingerprint=view["source_fingerprint"],
            phrase=rule.phrase,
            severity=rule.severity,
            matches=found,
            match_count=len(found),
        )
        db.add(detection)
        db.flush()
        # Speaker-only changes preserve historical evidence, but do not resend identical word matches.
        already_notified = any(
            p.rule_revision == rule.revision and p.source_fingerprint == view["source_fingerprint"] for p in prior
        )
        if found and rule.notify and not already_notified:
            for uid in rule.recipients:
                recipient = db.get(User, uid)
                if (
                    recipient
                    and recipient.active
                    and recipient.email_verified
                    and recipient.organization_id == call.organization_id
                ):
                    db.add(FlagNotification(detection_id=detection.id, recipient_id=uid))


def deliver_one(factory, settings, mail):
    # One worker. Claim before SMTP; interrupted/ambiguous sends are never retried automatically.
    with factory() as db:
        job = db.scalar(
            select(FlagNotification)
            .where(FlagNotification.status == "pending")
            .order_by(FlagNotification.created_at)
            .limit(1)
        )
        if job is None:
            return
        detection = db.get(FlagDetection, job.detection_id)
        call = db.get(Call, detection.call_id)
        recipient = db.get(User, job.recipient_id)
        rule = db.get(FlagRule, detection.rule_id)
        if (
            not recipient
            or not recipient.active
            or not recipient.email_verified
            or recipient.organization_id != call.organization_id
            or not rule.enabled
            or not rule.notify
            or rule.revision != detection.rule_revision
            or recipient.id not in rule.recipients
        ):
            job.status = "canceled"
            db.commit()
            return
        if not operational_access(recipient.organization, settings):
            job.status = "blocked"
            db.commit()
            return
        job.status, job.attempted_at = "sending", time.time()
        payload = (
            f"Organization: {recipient.organization.name}\nAudit: {call.audit_number}\n"
            f"Flagged phrase: {detection.phrase}\nOccurrences: {len(detection.matches)}\n"
            f"Review securely: {settings.frontend_origin}/calls/{call.id}\n"
            "Sign in with your organization account to review the evidence."
        )
        email, jid = recipient.email, job.id
        db.commit()
    try:
        mail.send(email, "flag", payload)
        status = "local" if settings.mail_delivery == "local" else "submitted"
    except Exception as exc:
        status = "uncertain"
        event("flag_mail_failed", notification_id=jid, error_type=type(exc).__name__)
    with factory() as db:
        job = db.get(FlagNotification, jid)
        if job:
            job.status = status
            db.commit()
