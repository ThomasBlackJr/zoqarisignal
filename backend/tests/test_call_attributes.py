from app.services.call_attributes import extract, normalize, sync_attributes
from app.models import Call, Transcript, CallAttribute, AttributeEvent, LEGACY_ORG, User
from sqlalchemy import select
from uuid import uuid4

TEXT = "This is John Smith calling about order 104582. It's supposed to go to 123 Main Street, Akron, Ohio. The HAWB is 123456789."


def test_extract_all_defaults_and_source_offsets():
    values = extract(TEXT, [{"text": TEXT, "start": 1.0, "end": 10.0, "speaker": None}], [])
    assert {k: v["value"] for k, v in values.items()} == {
        "customer": "John Smith",
        "order": "104582",
        "hawb": "123456789",
        "address": "123 Main Street, Akron, Ohio",
    }
    for value in values.values():
        assert TEXT[value["source_start"] : value["source_end"]] == value["value"]
        assert value["timestamp"] == 1.0


def test_missing_ambiguous_malformed_and_agent_names():
    assert extract("Hello, how are you?", [], []) == {}
    assert "order" not in extract("Order 12345 and order 67890.", [], [])
    for text in ["Order missing.", "HAWB unknown.", "Order 12.", "Order 123/456."]:
        assert extract(text, [], []) == {}
    text = "This is John Smith calling about order 12345."
    assert "customer" not in extract(
        text, [], [{"source_start": 0, "source_end": len(text), "effective_role": "DISPATCHER"}]
    )
    assert normalize("order", "AB-104 582") == normalize("order", "ab104582")
    assert normalize("order", "104582") != normalize("order", "104583")


def stored_call(app, text=TEXT):
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        call = Call(
            organization_id=LEGACY_ORG,
            filename="Synthetic.wav",
            storage_name=str(uuid4()) + ".wav",
            content_type="audio/wav",
            size_bytes=1,
            uploaded_by=user.id,
            status="completed",
        )
        db.add(call)
        db.flush()
        db.add(Transcript(call_id=call.id, text=text, segments=[], provider="demo", model="synthetic-test"))
        db.commit()
        return call.id


def test_persistence_idempotence_manual_removal_and_history(app):
    call_id = stored_call(app)
    with app.state.db() as db:
        call = db.get(Call, call_id)
        sync_attributes(db, call)
        db.commit()
        assert len(db.scalars(select(CallAttribute)).all()) == 4
        count = len(db.scalars(select(AttributeEvent)).all())
        sync_attributes(db, call)
        db.commit()
        assert len(db.scalars(select(AttributeEvent)).all()) == count
        row = db.scalar(select(CallAttribute).where(CallAttribute.key == "order"))
        row.origin = "manual"
        row.value = None
        row.normalized_value = None
        db.commit()
        sync_attributes(db, call)
        db.commit()
        assert db.get(CallAttribute, row.id).value is None
        assert call.transcript.text == TEXT


def test_concurrent_ingestion_during_cache_derivation_keeps_processing(app, signed_in, wav_bytes, monkeypatch):
    from sqlalchemy import update
    from app.models import Organization
    from app.services import processing
    from unittest.mock import Mock

    original = processing.conversation_for

    def concurrent_write(transcript):
        # A batch upload commits through a different connection between the
        # source read and the worker's cache/attribute writes.
        with app.state.db() as db:
            db.execute(update(Organization).where(Organization.id == LEGACY_ORG).values(name=Organization.name))
            db.commit()
        return original(transcript)

    monkeypatch.setattr(processing, "conversation_for", concurrent_write)
    call = signed_in.post("/calls", files={"file": ("synthetic.wav", wav_bytes, "audio/wav")}).json()["id"]
    processor = app.state.processor
    processor.transcription.transcribe = Mock(wraps=processor.transcription.transcribe)
    processor.qa.evaluate = Mock(wraps=processor.qa.evaluate)
    processor.process(call)
    with app.state.db() as db:
        assert db.get(Call, call).status == "completed"
        assert db.get(Call, call).transcript.text
        assert len(db.scalars(select(CallAttribute).where(CallAttribute.call_id == call)).all()) == 4
    assert processor.transcription.transcribe.call_count == processor.qa.evaluate.call_count == 1
