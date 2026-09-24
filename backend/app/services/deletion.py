"""Durable file cleanup after the database has atomically removed call content."""

from sqlalchemy import select, update
from ..models import PendingAudioDeletion, AdminEvent
from ..logging import event


def cleanup_audio(session_factory, settings, call_id=None):
    with session_factory() as db:
        query = select(PendingAudioDeletion)
        if call_id:
            query = query.where(PendingAudioDeletion.call_id == call_id)
        for candidate in db.scalars(query.limit(100)).all():
            claimed = db.execute(
                update(PendingAudioDeletion)
                .where(PendingAudioDeletion.call_id == candidate.call_id)
                .values(storage_name=PendingAudioDeletion.storage_name)
            )
            if claimed.rowcount != 1:
                continue
            pending = candidate
            root = settings.upload_dir.resolve()
            path = (root / pending.storage_name).resolve()
            try:
                if path.parent != root:
                    raise ValueError("invalid_storage_path")
                path.unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                event("audio_deletion_pending", pending.call_id, error_type=type(exc).__name__)
                continue
            audit = db.get(AdminEvent, pending.event_id)
            db.add(
                AdminEvent(
                    organization_id=audit.organization_id,
                    actor_id=audit.actor_id,
                    resource_type=audit.resource_type,
                    resource_id=audit.resource_id,
                    action="deleted",
                )
            )
            db.delete(pending)
            db.commit()
        return call_id is None or db.get(PendingAudioDeletion, call_id) is None
