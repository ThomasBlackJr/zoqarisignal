"""Synthetic regression for the live replay of call 4aaceed8-... .

The replay returned a non-verbatim (case-changed) quote and overall_score=90
despite category scores totaling 100. No customer transcript or response is
copied into this test. The original discarded response cannot be recovered.
"""

import json
from unittest.mock import Mock

import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError

from app.config import Settings
from app.models import Call, Status, Transcript
from app.services.providers import OpenAIQA
from app.services.qa_contract import evidence_sources, materialize, response_format
from app.services.qa_errors import QAReason, QAValidationError, failure_details
from app.services.rubric import RUBRIC, validate_result

TEXT = "Your delivery is confirmed. I will call you with an update."


def legacy_result():
    return {
        "overall_score": 90,
        "categories": [
            {
                "key": c["key"],
                "score": c["max_score"],
                "max_score": c["max_score"],
                "explanation": "Synthetic regression explanation.",
                "evidence": [],
            }
            for c in RUBRIC
        ],
        "summary": "Synthetic regression summary.",
        "strengths": [],
        "coaching_opportunities": [],
    }


def assessment():
    return {
        "categories": {
            c["key"]: {"score": c["max_score"], "explanation": "Synthetic explanation.", "evidence_ids": [0]}
            for c in RUBRIC
        },
        "summary": "Synthetic summary.",
        "strengths": [],
        "coaching_opportunities": [],
    }


def test_live_failure_condition_case_changed_evidence_masks_bad_total():
    old = legacy_result()
    old["categories"][3]["evidence"] = ["your delivery is confirmed."]
    with pytest.raises(QAValidationError) as error:
        validate_result(old, TEXT)
    assert error.value.safe_details() == {
        "validation_reason": "evidence_not_verbatim",
        "category_index": 3,
        "evidence_index": 0,
    }
    # Correcting the quotation must NOT cause the model's incorrect total to pass.
    old["categories"][3]["evidence"] = ["Your delivery is confirmed."]
    with pytest.raises(QAValidationError) as error:
        validate_result(old, TEXT)
    assert error.value.reason == QAReason.TOTAL


def test_source_references_and_derived_total_fix_the_contract_not_the_validator():
    sources = evidence_sources(TEXT)
    result = materialize(assessment(), sources, TEXT, response_format(len(sources)))
    assert result.overall_score == sum(c.score for c in result.categories) == 100
    assert result.categories[3].evidence == ["Your delivery is confirmed."]
    assert all(c.max_score == rubric["max_score"] for c, rubric in zip(result.categories, RUBRIC))
    assert validate_result(result, TEXT) == result
    # The provider is not permitted to sneak in a contradictory total.
    supplied_total = assessment() | {"overall_score": 90}
    with pytest.raises(ValidationError):
        materialize(supplied_total, sources, TEXT, response_format(len(sources)))


@pytest.mark.parametrize(
    "change",
    [
        "negative",
        "above_max",
        "float_score",
        "bool_score",
        "bad_id",
        "negative_id",
        "bool_id",
        "missing_category",
        "unknown_category",
        "raw_quote",
        "max_score",
    ],
)
def test_wire_contract_rejects_invalid_scores_and_references(change):
    value = assessment()
    category = value["categories"]["greeting"]
    if change == "negative":
        category["score"] = -1
    if change == "above_max":
        category["score"] = 11
    if change == "float_score":
        category["score"] = 5.5
    if change == "bool_score":
        category["score"] = True
    if change == "bad_id":
        category["evidence_ids"] = [1000]
    if change == "negative_id":
        category["evidence_ids"] = [-1]
    if change == "bool_id":
        category["evidence_ids"] = [True]
    if change == "missing_category":
        value["categories"].pop("closing")
    if change == "unknown_category":
        value["categories"]["invented"] = category
    if change == "raw_quote":
        category["evidence"] = ["Fabricated testimony."]
    if change == "max_score":
        category["max_score"] = 100
    with pytest.raises(ValidationError):
        materialize(value, evidence_sources(TEXT), TEXT, response_format(2))


def test_fabricated_or_case_changed_source_text_still_fails_final_validation():
    for source in ["your delivery is confirmed.", "The caller accepted a refund."]:
        with pytest.raises(QAValidationError) as error:
            materialize(assessment(), [source], TEXT, response_format(1))
        assert error.value.reason == QAReason.EVIDENCE_NOT_VERBATIM


def test_mutated_model_cannot_bypass_score_validation():
    schema = response_format(2)
    parsed = schema.model_validate(assessment())
    parsed.categories.greeting.score = 100
    with pytest.raises(ValidationError):
        materialize(parsed, evidence_sources(TEXT), TEXT, schema)
    result = materialize(assessment(), evidence_sources(TEXT), TEXT, schema)
    result.categories[0].score = -1
    with pytest.raises(ValidationError):
        validate_result(result, TEXT)


@pytest.mark.parametrize(
    "text",
    [
        TEXT,
        "  First line\nSecond line\r\nThird line  ",
        "We’ll call.\tDon't leave! Ready?",
        "x" * 1300,
        "No punctuation",
        "  ",
    ],
)
def test_evidence_spans_preserve_exact_source_characters(text):
    sources = evidence_sources(text)
    assert all(source and source in text and len(source) <= 600 for source in sources)
    assert "".join("".join(source.split()) for source in sources) == "".join(text.split())
    if not text.strip():
        with pytest.raises(QAValidationError):
            response_format(len(sources))


def mock_openai(monkeypatch, value):
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/responses"
        assert body["text"]["format"]["strict"] is True
        schema = body["text"]["format"]["schema"]
        assert "overall_score" not in schema["properties"]
        assert schema["$defs"]["QA_greeting"]["properties"]["score"]["maximum"] == 10
        return httpx.Response(
            200,
            json={
                "id": "resp_regression",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "gpt-4o-mini",
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
                "output": [
                    {
                        "id": "msg_regression",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": json.dumps(value), "annotations": []}],
                    }
                ],
            },
        )

    client = OpenAI(
        api_key="test-placeholder-not-a-real-key", http_client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    monkeypatch.setattr("app.services.providers.OpenAI", lambda **kwargs: client)
    return OpenAIQA(Settings(_env_file=None)), requests


def test_sdk_http_200_response_uses_exact_evidence_and_valid_total(monkeypatch):
    service, requests = mock_openai(monkeypatch, assessment())
    result = service.evaluate(TEXT)
    assert len(requests) == 1
    assert result.overall_score == 100
    assert result.categories[0].evidence == ["Your delivery is confirmed."]
    validate_result(result, TEXT)


def test_retry_saved_transcript_through_provider_without_retranscription(signed_in, app, wav_bytes, monkeypatch):
    call_id = signed_in.post("/calls", files={"file": ("call.wav", wav_bytes, "audio/wav")}).json()["id"]
    with app.state.db() as db:
        db.add(
            Transcript(call_id=call_id, text=TEXT, segments=[], provider="openai", model="whisper-1", created_at=123.0)
        )
        db.get(Call, call_id).status = Status.FAILED
        db.get(Call, call_id).failed_stage = "qa"
        db.commit()
    transcriber = Mock()
    transcriber.name = "openai"
    transcriber.transcribe.side_effect = AssertionError("Must not retranscribe saved audio")
    processor = app.state.processor
    processor.transcription = transcriber
    processor.qa, requests = mock_openai(monkeypatch, assessment())
    assert signed_in.post(f"/calls/{call_id}/retry").status_code == 200
    processor.process(call_id)
    detail = signed_in.get(f"/calls/{call_id}").json()
    assert detail["status"] == "completed" and detail["evaluation"]["overall_score"] == 100
    assert detail["transcript"]["text"] == TEXT
    with app.state.db() as db:
        assert db.get(Transcript, call_id).created_at == 123.0
    transcriber.transcribe.assert_not_called()
    assert len(requests) == 1


def test_specific_log_reason_without_transcript_or_provider_payload(signed_in, app, wav_bytes, caplog):
    call_id = signed_in.post("/calls", files={"file": ("call.wav", wav_bytes, "audio/wav")}).json()["id"]
    processor = app.state.processor
    processor.qa = Mock()
    processor.qa.name = "custom"
    bad = legacy_result()
    bad["categories"][3]["evidence"] = ["Private customer transcript must never be logged"]
    processor.qa.evaluate.return_value = bad
    with caplog.at_level("INFO", logger="drive"):
        processor.process(call_id)
    logs = [json.loads(record.message) for record in caplog.records if record.name == "drive"]
    failure = next(item for item in logs if item["event"] == "qa_failed")
    assert failure["validation_reason"] == "evidence_not_verbatim"
    assert failure["category_index"] == 3 and failure["evidence_index"] == 0
    assert "Private customer" not in caplog.text
    assert "Synthetic regression explanation" not in caplog.text
    detail = signed_in.get(f"/calls/{call_id}").json()
    assert detail["transcript"] is not None and detail["evaluation"] is None
    assert "evidence_not_verbatim" in detail["error"]


def test_schema_diagnostics_redact_values_and_untrusted_field_names():
    value = assessment()
    value["categories"]["greeting"]["score"] = "PRIVATE_VALUE_DO_NOT_LOG"
    value["PRIVATE_FIELD_DO_NOT_LOG"] = "PRIVATE_RESPONSE_DO_NOT_LOG"
    with pytest.raises(ValidationError) as error:
        response_format(2).model_validate(value)
    details = failure_details(error.value)
    assert details["validation_reason"] == "schema_invalid"
    assert {"path": ["categories", "greeting", "score"], "code": "int_type"} in details["schema_issues"]
    assert "PRIVATE" not in json.dumps(details)
