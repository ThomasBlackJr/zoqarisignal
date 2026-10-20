"""Content-free lifecycle audit; never store passwords, mail payloads, codes or tokens."""

from ..models import AccountEvent


def account_event(db, action, *, user=None, organization_id=None, actor=None, reason=None):
    db.add(
        AccountEvent(
            action=action,
            user_id=user.id if user else None,
            organization_id=organization_id or (user.organization_id if user else None),
            actor_id=actor.id if actor else None,
            reason=reason,
        )
    )
