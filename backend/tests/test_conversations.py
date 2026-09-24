import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text as sql

from app.conversation_schemas import SpeakerRole
from app.models import Call, Transcript
from app.schemas import Segment
from app.services.conversations import ConversationService, conversation_for
from app.services.providers import DEMO_LINES, DemoQA
from app.services.qa_contract import evidence_sources
from app.services.rubric import validate_result
from app.services.speaker_roles import LocalSpeakerRoles


def segment(words, start=None, end=None, speaker=None):
    return {"text": words, "start": start, "end": end, "speaker": speaker}


def derive(parts, text=None):
    return ConversationService().derive(text if text is not None else " ".join(p["text"] for p in parts), parts)


def test_same_known_speaker_merges_and_uses_final_end():
    parts = [
        segment("Thank you for calling dispatch.", 0, 4, "a"),
        segment("How can I help you?", 5, 5.8, "a"),
        segment("Can I get your route number?", 6, 6.4, "a"),
    ]
    result = derive(parts)
    assert len(result.turns) == 1
    turn = result.turns[0]
    assert (turn.start, turn.end) == (0, 6.4)
    assert turn.speaker_role == SpeakerRole.DISPATCHER
    assert turn.speaker_id == "a" and turn.segment_indices == [0, 1, 2]
    assert turn.confidence is None


def test_same_inferred_side_merges_without_fabricated_speaker_id():
    result = derive([segment("Thank you for calling.", 0, 4), segment("How can I help you?", 5, 8)])
    assert len(result.turns) == 1
    assert result.turns[0].speaker_role == SpeakerRole.DISPATCHER
    assert result.turns[0].speaker_id is None
    assert not result.has_speaker_ids


@pytest.mark.parametrize("ids", [("a", "b"), ("a", None), (None, "a")])
def test_different_identity_not_merged_even_with_same_role(ids):
    result = derive([segment("Thank you for calling.", 0, 4, ids[0]), segment("How can I help you?", 5, 8, ids[1])])
    assert len(result.turns) == 2
    assert all(t.speaker_role == SpeakerRole.DISPATCHER for t in result.turns)


def test_role_change_never_merged():
    result = derive(
        [
            segment("How can I help you?", 0, 4),
            segment("I'm calling because my delivery has not arrived.", 5, 8),
            segment("Can I get your route number?", 9, 12),
        ]
    )
    assert [t.speaker_role for t in result.turns] == [
        SpeakerRole.DISPATCHER,
        SpeakerRole.CALLER,
        SpeakerRole.DISPATCHER,
    ]


@pytest.mark.parametrize("identity", [None, "UNKNOWN", "?", " "])
def test_unknown_is_not_a_shared_speaker_identity(identity):
    result = derive([segment("Okay.", 0, 1, identity), segment("Yes.", 2, 3, identity)])
    assert len(result.turns) == 2
    assert all(t.speaker_role == SpeakerRole.UNKNOWN and t.speaker_id is None for t in result.turns)


def test_unknown_role_with_actual_shared_id_can_merge():
    result = derive([segment("Okay.", 0, 1, "speaker_7"), segment("Yes.", 2, 3, "speaker_7")])
    assert len(result.turns) == 1
    assert result.turns[0].speaker_role == SpeakerRole.UNKNOWN
    assert result.turns[0].speaker_id == "speaker_7"


def test_unknown_breaks_inferred_turn_and_first_speaker_order_does_not_assign_role():
    result = derive([segment("How can I help you?"), segment("Okay."), segment("How may I help you?")])
    assert len(result.turns) == 3
    roles = LocalSpeakerRoles().infer([Segment(text="Hello.", speaker="first"), Segment(text="Yes.", speaker="second")])
    assert all(role.speaker_role == SpeakerRole.UNKNOWN for role in roles)


def test_known_speaker_context_propagates_but_conflicting_cues_are_unknown():
    result = derive([segment("How can I help you?", 0, 1, "a"), segment("One moment.", 2, 3, "a")])
    assert result.turns[0].speaker_role == SpeakerRole.DISPATCHER
    conflict = derive([segment("How can I help you?", 0, 1, "a"), segment("I'm calling about a delivery.", 2, 3, "a")])
    assert all(t.speaker_role == SpeakerRole.UNKNOWN for t in conflict.turns)


def test_mixed_speakers_inside_one_raw_segment_remain_unknown():
    result = derive([segment("How can I help you? I'm calling about my delivery.", 0, 8)])
    assert result.turns[0].speaker_role == SpeakerRole.UNKNOWN


def test_provider_role_mapping_is_separate_from_generic_id():
    parts = [Segment(text="Hello.", speaker="a")]
    assert LocalSpeakerRoles().infer(parts)[0].speaker_role == SpeakerRole.UNKNOWN
    assignment = LocalSpeakerRoles({"a": SpeakerRole.DISPATCHER}).infer(parts)[0]
    assert assignment.speaker_role == SpeakerRole.DISPATCHER and assignment.role_source == "provided_role"


@pytest.mark.parametrize("last_end", [6.4, None])
def test_missing_end_is_not_replaced_with_final_start(last_end):
    turn = derive([segment("One.", 0, 4, "a"), segment("Two.", 5, last_end, "a")]).turns[0]
    assert turn.start == 0 and turn.end == last_end


def test_missing_start_stays_missing_and_overlapping_segments_are_not_collapsed():
    turn = derive([segment("One.", None, 3, "a"), segment("Two.", 4, 5, "a")]).turns[0]
    assert turn.start is None and turn.end == 5
    assert len(derive([segment("One.", 0, 8, "a"), segment("Two.", 5, 6, "a")]).turns) == 2


def test_exact_canonical_text_and_raw_segments_are_unchanged():
    original = "  Hello.\n\n  How can I help you?\tCan I get your route number?  "
    parts = [
        segment(" Hello.", 0, 1, "a"),
        segment(" How can I help you?", 2, 4, "a"),
        segment("Can I get your route number? ", 5, 6, "a"),
    ]
    before = copy.deepcopy(parts)
    result = derive(parts, original)
    assert parts == before
    assert "".join(t.text for t in result.turns) == original
    assert all(t.text == original[t.source_start : t.source_end] for t in result.turns)


@pytest.mark.parametrize("parts", [[], [segment("Different words.", 0, 2)], [segment("Repeated.")]])
def test_unalignable_or_text_only_legacy_transcript_uses_complete_original(parts):
    original = "Unchanged original text. Repeated. Repeated."
    result = derive(parts, original)
    assert result.alignment == "full_text_fallback"
    assert result.turns[0].text == original
    assert result.turns[0].speaker_role == SpeakerRole.UNKNOWN
    assert result.turns[0].start is None and result.turns[0].end is None


def test_formatting_failure_falls_back_without_sensitive_logs(caplog):
    original = "PRIVATE TRANSCRIPT"
    transcript = SimpleNamespace(
        call_id="test", text=original, segments=[{"text": original, "start": -1}], conversation=None
    )
    result = conversation_for(transcript)
    assert result["turns"][0]["text"] == original
    assert result["turns"][0]["speaker_role"] == "UNKNOWN"
    assert "PRIVATE" not in caplog.text


def test_stale_cache_is_rederived_without_changing_raw_data():
    transcript = SimpleNamespace(
        call_id="test", text="How can I help you?", segments=[segment("How can I help you?")], conversation=None
    )
    transcript.conversation = conversation_for(transcript)
    transcript.text = "Yes."
    transcript.segments = [segment("Yes.")]
    result = conversation_for(transcript)
    assert result["turns"][0]["text"] == "Yes."
    assert result["turns"][0]["speaker_role"] == "UNKNOWN"


def test_existing_call_read_formats_without_any_provider_requests(signed_in, app, wav_bytes):
    call_id = signed_in.post("/calls", files={"file": ("call.wav", wav_bytes, "audio/wav")}).json()["id"]
    original = "Thank you for calling. How can I help you?"
    parts = [segment("Thank you for calling.", 0, 0.4), segment("How can I help you?", 0.5, 1)]
    with app.state.db() as db:
        db.add(Transcript(call_id=call_id, text=original, segments=parts, provider="openai", model="whisper-1"))
        db.get(Call, call_id).status = "failed"
        db.commit()
    processor = app.state.processor
    processor.transcription = Mock()
    processor.qa = Mock()
    for _ in range(2):
        data = signed_in.get(f"/calls/{call_id}").json()
        assert len(data["transcript"]["conversation"]["turns"]) == 1
        assert data["transcript"]["text"] == original
        assert data["transcript"]["segments"] == parts
    processor.transcription.transcribe.assert_not_called()
    processor.qa.evaluate.assert_not_called()
    with app.state.db() as db:
        assert db.get(Transcript, call_id).conversation is None  # GET did not write a cache.


def test_grouping_does_not_change_numbered_qa_excerpts_or_evidence():
    original = "\n".join(DEMO_LINES)
    parts = [segment(line) for line in DEMO_LINES]
    before = evidence_sources(original)
    result = derive(parts, original)
    assert "".join(t.text for t in result.turns) == original
    assert evidence_sources(original) == before
    assert validate_result(DemoQA().evaluate(original), original).overall_score == 90


def test_new_transcripts_cache_conversation_without_breaking_qa(signed_in, app, wav_bytes):
    call_id = signed_in.post("/calls", files={"file": ("call.wav", wav_bytes, "audio/wav")}).json()["id"]
    app.state.processor.process(call_id)
    with app.state.db() as db:
        transcript = db.get(Transcript, call_id)
        assert transcript.conversation is not None
        assert "".join(t["text"] for t in transcript.conversation["turns"]) == transcript.text
        assert db.get(Call, call_id).status == "completed"


def test_conversation_cache_failure_does_not_fail_qa(signed_in, app, wav_bytes, monkeypatch):
    call_id = signed_in.post("/calls", files={"file": ("call.wav", wav_bytes, "audio/wav")}).json()["id"]

    def fail(*args):
        raise RuntimeError("Formatting failed")

    monkeypatch.setattr("app.services.processing.conversation_for", fail)
    app.state.processor.process(call_id)
    with app.state.db() as db:
        assert db.get(Call, call_id).status == "completed"
        assert db.get(Transcript, call_id).text == "\n".join(DEMO_LINES)


def test_migration_preserves_legacy_transcript(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "a2623e115e90")
    engine = create_engine(url)
    with engine.begin() as conn:
        # Minimal old-schema fixture; no customer data and no model create_all.
        conn.execute(sql("INSERT INTO users VALUES ('u', 'x@example.test', 'Test', 'test-hash', 'ADMIN', 1)"))
        conn.execute(
            sql(
                "INSERT INTO calls (id,filename,storage_name,content_type,size_bytes,created_at,status,is_demo,uploaded_by) VALUES ('c','c.wav','c.wav','audio/wav',1,0,'completed',0,'u')"
            )
        )
        conn.execute(
            sql(
                "INSERT INTO transcripts (call_id,text,segments,provider,model,created_at) VALUES ('c',:text,:segments,'openai','whisper-1',0)"
            ),
            {"text": "Yes.", "segments": json.dumps([segment("Yes.")])},
        )
    command.upgrade(Config("alembic.ini"), "head")
    with engine.connect() as conn:
        row = conn.execute(sql("SELECT text,segments,conversation FROM transcripts WHERE call_id='c'")).one()
        assert row[0] == "Yes." and json.loads(row[1]) == [segment("Yes.")] and row[2] is None
    assert "conversation" in {c["name"] for c in inspect(engine).get_columns("transcripts")}
    command.downgrade(Config("alembic.ini"), "a2623e115e90")
    with engine.connect() as conn:
        assert conn.execute(sql("SELECT text FROM transcripts WHERE call_id='c'")).scalar_one() == "Yes."
    engine.dispose()
