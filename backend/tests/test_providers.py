from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

from app.auth import get_db
from app.config import Settings
from app.services.providers import OpenAIQA, OpenAITranscription


def test_openai_transcription_adapter_preserves_segments(monkeypatch, tmp_path):
    client = Mock()
    client.audio.transcriptions.create.return_value.model_dump.return_value = {
        "text": "Good morning",
        "duration": 2.3,
        "segments": [{"start": 0.1, "end": 2.1, "text": "Good morning"}],
    }
    monkeypatch.setattr("app.services.providers.OpenAI", lambda **kwargs: client)
    service = OpenAITranscription(Settings(_env_file=None))
    path = tmp_path / "recording.wav"
    path.write_bytes(b"test adapter payload")
    result = service.transcribe(path)
    assert result.segments[0].start == 0.1 and result.duration == 2.3
    kwargs = client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["response_format"] == "verbose_json"
    assert kwargs["timestamp_granularities"] == ["segment"]
    assert kwargs["file"].closed


def test_qa_refusal_is_a_failure_not_an_evaluation(monkeypatch):
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(output_parsed=None)
    monkeypatch.setattr("app.services.providers.OpenAI", lambda **kwargs: client)
    service = OpenAIQA(Settings(_env_file=None))
    with pytest.raises(ValueError, match="provider_refused_or_incomplete"):
        service.evaluate("Untrusted transcript text")
    assert client.responses.parse.call_args.kwargs["store"] is False
    import json

    payload = json.loads(client.responses.parse.call_args.kwargs["input"][1]["content"])
    assert payload == {"transcript_excerpts": [{"id": 0, "text": "Untrusted transcript text"}]}


def test_database_failures_return_safe_error(client, app):
    def broken_db():
        raise OperationalError("sensitive SQL", {}, RuntimeError("sensitive connection string"))

    app.dependency_overrides[get_db] = broken_db
    response = client.get("/dashboard")
    assert response.status_code == 503
    assert "sensitive" not in response.text


def test_validation_errors_do_not_echo_passwords(signed_in):
    response = signed_in.post("/users", json={"email": "bad", "password": "secret", "name": "User"})
    assert response.status_code == 422
    assert "secret" not in response.text


def test_real_providers_require_configuration():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, transcription_provider="openai", qa_provider="openai", openai_api_key="")


def test_corrected_roles_are_separate_from_unchanged_evidence(monkeypatch):
    import json

    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(output_parsed=None)
    monkeypatch.setattr("app.services.providers.OpenAI", lambda **kwargs: client)
    service = OpenAIQA(Settings(_env_file=None))
    text = "The customer offered a solution."
    with pytest.raises(ValueError, match="provider_refused_or_incomplete"):
        service.evaluate(
            text,
            speaker_context={"turns": [{"source_start": 0, "source_end": len(text), "role": "CALLER", "manual": True}]},
        )
    request = client.responses.parse.call_args.kwargs
    payload = json.loads(request["input"][1]["content"])
    assert payload["transcript_excerpts"] == [{"id": 0, "text": text}]
    assert payload["speaker_turns"] == [{"role": "CALLER", "manual": True, "text": text}]
    assert "Never credit the employee" in request["input"][0]["content"]
    assert request["store"] is False
