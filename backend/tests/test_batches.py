import time
from sqlalchemy import select, func
from app.models import Call, Organization, UploadItem, LEGACY_ORG
from .test_supervisor_controls import other_tenant


def manifest(client, names, key="batch-request-key-0001"):
    response = client.post(
        "/batches", json={"request_key": key, "files": [{"filename": name, "size_bytes": size} for name, size in names]}
    )
    assert response.status_code == 201, response.text
    return response.json()


def put(client, batch, index, audio, name="recording.wav"):
    return client.post(
        f"/batches/{batch['id']}/items/{batch['items'][index]['id']}/upload", files={"file": (name, audio, "audio/wav")}
    )


def test_fifty_files_persist_and_complete_independently(signed_in, app, wav_bytes):
    batch = manifest(signed_in, [(f"volume-{i}.wav", len(wav_bytes)) for i in range(50)])
    for i in range(50):
        assert put(signed_in, batch, i, wav_bytes[:-1] + bytes([i])).status_code == 200
    queued = signed_in.get("/batches/" + batch["id"]).json()
    assert queued["counts"]["queued"] == 50
    for item in queued["items"]:
        app.state.processor.process(item["call_id"])
    result = signed_in.get("/batches/" + batch["id"]).json()
    assert result["counts"]["completed"] == 50
    assert result["counts"]["failed"] == 0
    assert signed_in.get("/calls").json()["total"] == 50


def test_ten_files_partial_failure_persisted_states_and_duplicate_protection(signed_in, app, wav_bytes):
    batch = manifest(signed_in, [(f"call-{i}.wav", len(wav_bytes)) for i in range(10)] + [("bad.txt", 12)])
    assert batch["counts"]["awaiting_upload"] == 10 and batch["counts"]["failed"] == 1
    for i in range(10):
        audio = wav_bytes[:-1] + bytes([i])
        assert put(signed_in, batch, i, audio, f"call-{i}.wav").status_code == 200
    current = signed_in.get("/batches/" + batch["id"]).json()
    assert current["counts"]["queued"] == 10
    assert signed_in.get("/calls").json()["total"] == 10
    for item in current["items"]:
        if item["call_id"]:
            app.state.processor.process(item["call_id"])
    after = signed_in.get("/batches/" + batch["id"]).json()
    assert after["counts"]["completed"] == 10 and after["counts"]["failed"] == 1
    assert signed_in.get("/batches").json()["items"][0] == after
    duplicate = manifest(signed_in, [("same-audio.wav", len(wav_bytes))], "another-batch-key-0002")
    linked = put(signed_in, duplicate, 0, wav_bytes).json()
    assert linked["items"][0]["duplicate"] is True
    assert linked["counts"]["completed"] == 1
    assert signed_in.get("/calls").json()["total"] == 10


def test_malformed_file_can_be_replaced_without_affecting_success(signed_in, app, wav_bytes):
    batch = manifest(signed_in, [("good.wav", len(wav_bytes)), ("bad.wav", 6)])
    put(signed_in, batch, 0, wav_bytes)
    failed = put(signed_in, batch, 1, b"broken").json()
    assert failed["counts"]["failed"] == 1 and failed["counts"]["queued"] == 1
    assert "content" in failed["items"][1]["error"]
    repaired = put(signed_in, batch, 1, wav_bytes[:-1] + b"z", "replacement.wav").json()
    assert repaired["counts"]["failed"] == 0 and repaired["counts"]["queued"] == 2
    assert repaired["items"][1]["filename"] == "replacement.wav"


def test_manifest_and_item_retries_are_idempotent(signed_in, app, wav_bytes):
    batch = manifest(signed_in, [("one.wav", len(wav_bytes))])
    again = manifest(signed_in, [("one.wav", len(wav_bytes))])
    assert batch["id"] == again["id"]
    assert (
        signed_in.post(
            "/batches",
            json={"request_key": "batch-request-key-0001", "files": [{"filename": "other.wav", "size_bytes": 12}]},
        ).status_code
        == 409
    )
    first = put(signed_in, batch, 0, wav_bytes).json()
    second = put(signed_in, batch, 0, wav_bytes).json()
    assert first["items"][0]["call_id"] == second["items"][0]["call_id"]
    assert signed_in.get("/calls").json()["total"] == 1


def test_inflight_and_expired_upload_lease(signed_in, app, wav_bytes):
    batch = manifest(signed_in, [("one.wav", len(wav_bytes))])
    with app.state.db() as db:
        item = db.get(UploadItem, batch["items"][0]["id"])
        item.status = "uploading"
        item.updated_at = time.time()
        db.commit()
    assert put(signed_in, batch, 0, wav_bytes).status_code == 409
    with app.state.db() as db:
        db.get(UploadItem, batch["items"][0]["id"]).updated_at = time.time() - 601
        db.commit()
    assert signed_in.get("/batches/" + batch["id"]).json()["items"][0]["status"] == "failed"
    assert put(signed_in, batch, 0, wav_bytes).json()["counts"]["queued"] == 1


def test_failed_processing_retry_keeps_batch_and_transcript(signed_in, app, wav_bytes):
    batch = manifest(signed_in, [("one.wav", len(wav_bytes))])
    cid = put(signed_in, batch, 0, wav_bytes).json()["items"][0]["call_id"]
    original = app.state.processor.qa.evaluate

    def failure(*args, **kwargs):
        raise ValueError("private payload")

    app.state.processor.qa.evaluate = failure
    app.state.processor.process(cid)
    assert signed_in.get("/batches/" + batch["id"]).json()["counts"]["failed"] == 1
    with app.state.db() as db:
        saved = db.get(Call, cid).transcript.text
    app.state.processor.qa.evaluate = original

    def forbidden(*args):
        raise AssertionError("Retranscription is forbidden")

    app.state.processor.transcription.transcribe = forbidden
    assert signed_in.post(f"/calls/{cid}/retry").status_code == 200
    app.state.processor.process(cid)
    assert signed_in.get("/batches/" + batch["id"]).json()["counts"]["completed"] == 1
    assert signed_in.get(f"/calls/{cid}").json()["transcript"]["text"] == saved


def test_cross_tenant_batches_and_items_not_visible(signed_in, app, wav_bytes):
    batch = manifest(signed_in, [("one.wav", len(wav_bytes))])
    put(signed_in, batch, 0, wav_bytes)
    other_tenant(app)
    signed_in.post("/auth/login", json={"email": "other@example.test", "password": "test-password-only"})
    assert signed_in.get("/batches").json()["total"] == 0
    assert signed_in.get("/batches/" + batch["id"]).status_code == 404
    assert put(signed_in, batch, 0, wav_bytes).status_code == 404
    own = manifest(signed_in, [("one.wav", len(wav_bytes))])
    result = put(signed_in, own, 0, wav_bytes).json()
    assert result["items"][0]["duplicate"] is False
    foreign_item = signed_in.post(
        f"/batches/{own['id']}/items/{batch['items'][0]['id']}/upload", files={"file": ("x.wav", wav_bytes)}
    )
    assert foreign_item.status_code == 404


def test_entitlement_and_roles_block_batches(signed_in, app, wav_bytes):
    batch = manifest(signed_in, [("one.wav", len(wav_bytes))])
    with app.state.db() as db:
        db.get(Organization, LEGACY_ORG).subscription_status = "inactive"
        db.commit()
    assert signed_in.get("/batches").status_code == 403
    assert (
        signed_in.post(
            "/batches", json={"request_key": "blocked-key-0001", "files": [{"filename": "one.wav", "size_bytes": 1}]}
        ).status_code
        == 403
    )
    assert put(signed_in, batch, 0, wav_bytes).status_code == 403
    with app.state.db() as db:
        assert db.scalar(select(func.count()).select_from(Call)) == 0


def test_batch_limits_and_bad_metadata_isolation(signed_in):
    assert signed_in.post("/batches", json={"request_key": "batch-key-000001", "files": []}).status_code == 422
    batch = manifest(signed_in, [("empty.wav", 0), ("big.wav", 2 * 1048576), ("valid.wav", 120)])
    assert batch["counts"]["failed"] == 2 and batch["counts"]["awaiting_upload"] == 1
