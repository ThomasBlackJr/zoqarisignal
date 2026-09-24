import threading

from sqlalchemy import select, update

from ..logging import event
from ..models import Call, Evaluation, Status, Transcript, Rubric, FlagNotification
from .flags import detect, deliver_one
from .account_mail import build_mail
from ..schemas import Transcription
from .conversations import conversation_for, fingerprint
from .qa_errors import failure_details, QAReason, QAValidationError
from .rubric import active_rubric, rubric_items, validate_result
from .entitlements import assert_worker_access, EntitlementRequired
from .performance import snapshot_context
from .deletion import cleanup_audio


class Processor:
    def __init__(self, db, settings, transcription, qa):
        self.db = db
        self.settings = settings
        self.transcription = transcription
        self.qa = qa
        self.mail = build_mail(settings)
        self.stop_event = threading.Event()
        self.thread = None

    def recover(self):
        with self.db() as db:
            db.execute(update(FlagNotification).where(FlagNotification.status == "sending").values(status="uncertain"))
            db.execute(
                update(Call)
                .where(Call.status.in_([Status.TRANSCRIBING, Status.ANALYZING]))
                .values(
                    status=Status.FAILED,
                    error="Processing was interrupted by a server restart. Retry to continue.",
                    failed_stage="interrupted",
                )
            )
            db.commit()

    def process(self, call_id):
        stage = "transcription"
        try:
            with self.db() as db:
                claimed = db.execute(
                    update(Call)
                    .where(Call.id == call_id, Call.status == Status.QUEUED)
                    .values(status=Status.TRANSCRIBING)
                )
                db.commit()
                if claimed.rowcount != 1:
                    return
                call = db.get(Call, call_id)
                assert_worker_access(db, call.organization_id, self.settings)
                # A retry can run after a provider configuration change.
                # Never label synthetic output as a real call evaluation.
                call.is_demo = bool(call.is_demo or self.transcription.name == "demo" or self.qa.name == "demo")
                db.commit()
                if call.transcript is None:
                    event("transcription_started", call_id)
                    output = Transcription.model_validate(
                        self.transcription.transcribe(self.settings.upload_dir / call.storage_name)
                    )
                    db.add(
                        Transcript(
                            call_id=call_id,
                            text=output.text,
                            segments=[s.model_dump() for s in output.segments],
                            provider=self.transcription.name,
                            model=self.transcription.model,
                        )
                    )
                    if output.duration is not None:
                        call.duration = output.duration
                    db.commit()
                    db.refresh(call)
                    event("transcription_completed", call_id)
                # Derived presentation must never invalidate a saved transcript
                # or prevent QA from consuming its original text.
                try:
                    with db.begin_nested():
                        call.transcript.conversation = conversation_for(call.transcript)
                except Exception as exc:
                    event("conversation_cache_failed", call_id, error_type=type(exc).__name__)
                stage = "flags"
                detect(db, call)
                db.commit()
                stage = "qa"
                call.status = Status.ANALYZING
                db.commit()
                event("qa_started", call_id)
                rubric = (
                    db.get(Rubric, call.requested_rubric_id)
                    if call.requested_rubric_id
                    else active_rubric(db, call.organization_id)
                )
                if rubric.organization_id != call.organization_id:
                    raise ValueError("rubric_organization_mismatch")
                call.requested_rubric_id = rubric.id
                if call.requested_transcript_context is None:
                    call.requested_transcript_context = snapshot_context(db, call.transcript)
                context = call.requested_transcript_context
                db.commit()
                items = rubric_items(rubric)
                # Recheck after transcription: a canceled/expired grant must not incur QA cost.
                assert_worker_access(db, call.organization_id, self.settings)
                if context["source_fingerprint"] != fingerprint(call.transcript.text, call.transcript.segments):
                    raise QAValidationError(QAReason.TRANSCRIPT_CONTEXT)
                options = {"rubric": items}
                if context["revision"]:
                    options["speaker_context"] = context
                result = validate_result(self.qa.evaluate(call.transcript.text, **options), call.transcript.text, items)
                db.add(
                    Evaluation(
                        call_id=call_id,
                        overall_score=result.overall_score,
                        transcript_revision=context["revision"],
                        transcript_context=context,
                        result=result.model_dump(),
                        rubric_version=rubric.version,
                        rubric_id=rubric.id,
                        provider=self.qa.name,
                        model=self.qa.model,
                    )
                )
                call.requested_rubric_id = None
                call.requested_transcript_context = None
                call.status = Status.COMPLETED
                call.error = None
                call.failed_stage = None
                db.commit()
                event("qa_completed", call_id, score=result.overall_score)
        except EntitlementRequired:
            with self.db() as db:
                call = db.get(Call, call_id)
                if call:
                    call.status = Status.FAILED
                    call.failed_stage = "entitlement"
                    call.error = "Operational access is inactive. Restore access, then Retry. Saved transcripts and evaluations are preserved."
                    db.commit()
            event("processing_access_denied", call_id, validation_reason="entitlement_required")
        except Exception as exc:
            diagnostics = failure_details(exc) if stage == "qa" else {}
            event(f"{stage}_failed", call_id, error_type=type(exc).__name__, **diagnostics)
            try:
                with self.db() as db:
                    call = db.get(Call, call_id)
                    if call:
                        call.status = Status.FAILED
                        call.failed_stage = stage
                        if stage == "qa":
                            call.error = f"QA failed ({diagnostics['validation_reason']}). The transcript is preserved. Retry QA after checking the validation reason in the backend log."
                        else:
                            call.error = f"{stage.upper()} failed ({type(exc).__name__}). Check the configured provider, credentials, and service availability, then retry."
                        db.commit()
            except Exception as db_exc:
                event("failure_persistence_failed", call_id, error_type=type(db_exc).__name__)

    def run(self):
        while not self.stop_event.is_set():
            try:
                cleanup_audio(self.db, self.settings)
                deliver_one(self.db, self.settings, self.mail)
                with self.db() as db:
                    call_id = db.scalar(
                        select(Call.id).where(Call.status == Status.QUEUED).order_by(Call.created_at).limit(1)
                    )
                if call_id:
                    self.process(call_id)
                    continue
            except Exception as exc:
                event("worker_poll_failed", error_type=type(exc).__name__)
            self.stop_event.wait(1)

    def start(self):
        self.recover()
        self.thread = threading.Thread(target=self.run, daemon=True, name="drive-processor")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
