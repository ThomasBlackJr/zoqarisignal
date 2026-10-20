from types import SimpleNamespace
from unittest.mock import Mock
from app.config import Settings
from app.services.company_context import vocabulary, provider_prompt, company_annotations
from app.services.providers import OpenAITranscription, DemoTranscription


def org(name):
    return SimpleNamespace(name=name, transcription_vocabulary=None)


def test_registered_default_existing_org_and_tenant_isolation():
    a = vocabulary(org("ABC Pool Corp"))
    b = vocabulary(org("XYZ Automotive"))
    assert "ABC Pool Corp" in provider_prompt(a)
    assert "ABC Pool Corp" not in provider_prompt(b)
    text = "Thank you for calling ABC Pull Court."
    assert company_annotations(text, a)[0]["replacement"] == "ABC Pool Corp"
    assert company_annotations(text, b) == []


def test_conservative_context_and_original_offsets():
    text = "Thank you for calling ABC Pull Court. This is Sarah."
    correction = company_annotations(text, vocabulary(org("ABC Pool Corp")))[0]
    assert text[correction["source_start"] : correction["source_end"]] == correction["original"]
    for unrelated in [
        "I saw ABC Pull Court yesterday.",
        "Thank you for calling the court about a pool.",
        "Thanks for calling XYZ Pool Corp.",
        "Thank you for calling ABC Pool Corp.",
    ]:
        assert company_annotations(unrelated, vocabulary(org("ABC Pool Corp"))) == []


def test_provider_supported_prompt_and_unchanged_demo(monkeypatch, tmp_path):
    client = Mock()
    client.audio.transcriptions.create.return_value.model_dump.return_value = {"text": "Hello", "segments": []}
    monkeypatch.setattr("app.services.providers.OpenAI", lambda **_: client)
    service = OpenAITranscription(Settings(_env_file=None))
    path = tmp_path / "audio.wav"
    path.write_bytes(b"test")
    service.transcribe(path, context=vocabulary(org("ABC Pool Corp")))
    assert "ABC Pool Corp" in client.audio.transcriptions.create.call_args.kwargs["prompt"]
    service.model = "gpt-4o-transcribe-diarize"
    service.transcribe(path, context=vocabulary(org("ABC Pool Corp")))
    assert "prompt" not in client.audio.transcriptions.create.call_args.kwargs
    assert (
        DemoTranscription().transcribe(path).text
        == DemoTranscription().transcribe(path, context=vocabulary(org("ABC"))).text
    )


def test_worker_uses_registered_company_automatically(app, signed_in, wav_bytes):
    from app.models import Organization, LEGACY_ORG, Call, CallAttribute
    from sqlalchemy import select

    with app.state.db() as db:
        db.get(Organization, LEGACY_ORG).name = "ABC Pool Corp"
        db.commit()
    call = signed_in.post("/calls", files={"file": ("synthetic.wav", wav_bytes, "audio/wav")}).json()["id"]
    service = app.state.processor.transcription
    service.transcribe = Mock(wraps=service.transcribe)
    app.state.processor.process(call)
    assert service.transcribe.call_args.kwargs["context"]["registered_name"] == "ABC Pool Corp"
    with app.state.db() as db:
        assert db.get(Call, call).status == "completed"
        assert len(db.scalars(select(CallAttribute).where(CallAttribute.call_id == call)).all()) == 4
