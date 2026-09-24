import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Form, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import delete, func, select, update, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from .admin_routes import router as admin_router
from .briefing_routes import router as briefing_router
from .flag_routes import router as flag_router
from .import_routes import router as import_router
from .billing_routes import router as billing_router
from .services.billing import StripeBilling
from .auth import COOKIE, current_user, dummy_hash, find_user, get_db, hasher, require, token_hash, user_view, verify
from .config import Settings
from .db import make_database
from .logging import event
from .models import Call, Evaluation, Session, Status, User, SpeakerCorrection
from .schemas import Login, NewUser
from .services.ingestion import ingest
from .services.flags import current_flag_query
from .services.hierarchy import manager_filter, employee_in_org
from .hierarchy_routes import router as hierarchy_router
from .batch_routes import router as batch_router
from .preference_routes import router as preference_router
from .team_routes import router as team_router
from .employee_routes import router as employee_router
from .services.performance import evaluated_view, current_performance
from .services.conversations import conversation_for
from .services.processing import Processor
from .services.providers import build_services, build_coaching
from .services.rubric import active_rubric, rubric_items
from .services.reviews import evaluation_view, corrected_conversation
from .review_routes import router as review_router
from .account_routes import router as account_router, AccountLimiter, issue_session
from .services.account_mail import build_mail
from typing import Literal


def call_view(call: Call, detail=False, db=None, flagged=None):
    qa = evaluated_view(call, db) if db else (evaluation_view(call.evaluation) if call.evaluation else None)
    data = {
        "id": call.id,
        "filename": call.filename,
        "audit_number": call.audit_number,
        "flagged": bool(db.scalar(select(Call.id).where(Call.id == call.id, current_flag_query().exists())))
        if db and flagged is None
        else bool(flagged),
        "employee_id": call.employee_id,
        "employee_name": call.employee.name if call.employee else None,
        "assignment_revision": call.assignment_revision,
        "evaluation_stale": qa.get("stale", False) if qa else False,
        "created_at": call.created_at,
        "duration": call.duration,
        "status": call.status,
        "size_bytes": call.size_bytes,
        "is_demo": call.is_demo,
        "error": call.error,
        "failed_stage": call.failed_stage,
        "qa_score": qa["final_score"] if qa and not qa.get("stale") else None,
        "ai_score": qa["overall_score"] if qa else None,
        "has_overrides": qa["has_overrides"] if qa else False,
        "review_status": (
            "needs_evaluation" if qa.get("stale") else "reviewed" if qa["reviewed_at"] else "needs_review"
        )
        if qa
        else "pending",
    }
    if detail:
        data["transcript"] = (
            {
                "text": call.transcript.text,
                "segments": call.transcript.segments,
                "conversation": corrected_conversation(call.transcript, db)
                if db
                else conversation_for(call.transcript),
                "provider": call.transcript.provider,
                "model": call.transcript.model,
            }
            if call.transcript
            else None
        )
        data["evaluation"] = qa
    return data


def create_app(settings: Settings | None = None, services=None):
    settings = settings or Settings()
    engine, factory = make_database(settings.database_url)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    transcription, qa = services or build_services(settings)
    processor = Processor(factory, settings, transcription, qa)

    @asynccontextmanager
    async def lifespan(app):
        if settings.worker_enabled:
            processor.start()
        yield
        processor.stop()
        engine.dispose()

    app = FastAPI(title="Zoqari Signal API", lifespan=lifespan)
    app.include_router(admin_router)
    app.include_router(briefing_router)
    app.include_router(flag_router)
    app.include_router(import_router)
    app.include_router(billing_router)
    app.include_router(review_router)
    app.include_router(account_router)
    app.include_router(batch_router)
    app.include_router(employee_router)
    app.include_router(hierarchy_router)
    app.include_router(team_router)
    app.include_router(preference_router)
    app.state.settings = settings
    app.state.coaching = build_coaching(settings)
    app.state.coaching_lock = threading.Lock()
    app.state.mail = build_mail(settings)
    app.state.billing = StripeBilling(settings)
    app.state.account_limiter = AccountLimiter()
    app.state.db = factory
    app.state.engine = engine
    app.state.processor = processor
    attempts = defaultdict(deque)
    attempt_lock = threading.Lock()

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not (
            request.method == "POST" and request.url.path == "/billing/webhook"
        ):
            origin = request.headers.get("origin")
            if origin and origin != settings.frontend_origin:
                return JSONResponse({"detail": "Untrusted request origin"}, status_code=403)
            if request.headers.get("x-drive-request") != "1":
                return JSONResponse({"detail": "Missing request verification header"}, status_code=403)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > settings.max_upload_mb * 1024 * 1024 + 65536):
            return JSONResponse({"detail": "Recording exceeds the configured upload size limit"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        event("database_error", error_type=type(exc).__name__)
        return JSONResponse({"detail": "Database temporarily unavailable. Please try again."}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default includes rejected inputs, which could echo a password.
        fields = sorted({str(error["loc"][-1]) for error in exc.errors()})
        return JSONResponse({"detail": "Invalid request. Check: " + ", ".join(fields)}, status_code=422)

    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        event("storage_error", error_type=type(exc).__name__)
        return JSONResponse(
            {"detail": "Recording storage is unavailable. Please contact your administrator."}, status_code=503
        )

    @app.get("/health")
    def health(db=Depends(get_db)):
        db.execute(select(1))
        return {"status": "ok"}

    @app.post("/auth/login")
    def login(body: Login, request: Request, response: Response, db=Depends(get_db)):
        key = request.client.host if request.client else "unknown"
        now = time.time()
        with attempt_lock:
            # Bounded per-process limiter; use an edge/shared limiter before multi-instance deployment.
            for expired in [k for k, v in attempts.items() if not v or v[-1] < now - 300]:
                del attempts[expired]
            recent = attempts[key]
            while recent and recent[0] < now - 300:
                recent.popleft()
            if len(recent) >= 10:
                raise HTTPException(429, "Too many sign-in attempts. Try again in five minutes.")
            recent.append(now)
        user = find_user(db, body.email)
        valid = verify(body.password, user.password_hash if user else dummy_hash)
        if not user or not valid or not user.active:
            raise HTTPException(401, "Email or password is incorrect")
        if hasher.check_needs_rehash(user.password_hash):
            user.password_hash = hasher.hash(body.password)
        issue_session(db, user, request, response)
        return user_view(user)

    @app.post("/auth/logout", status_code=204)
    def logout(request: Request, response: Response, db=Depends(get_db)):
        token = request.cookies.get(COOKIE)
        if token:
            db.execute(delete(Session).where(Session.token_hash == token_hash(token)))
            db.commit()
        response.delete_cookie(COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="strict")

    @app.get("/auth/me")
    def me(user=Depends(current_user)):
        return user_view(user)

    @app.post("/users", status_code=201)
    def add_user(body: NewUser, user=Depends(require("manage_users")), db=Depends(get_db)):
        if body.role == "OWNER":
            raise HTTPException(403, "Owner assignment is reserved for organization creation")
        created = User(
            email=body.email,
            name=body.name.strip(),
            role=body.role,
            organization_id=user.organization_id,
            password_hash=hasher.hash(body.password),
        )
        db.add(created)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "A user with that email already exists") from exc
        return user_view(created)

    @app.get("/config")
    def config(user=Depends(require("review")), db=Depends(get_db)):
        try:
            rubric = active_rubric(db, user.organization_id)
        except ValueError:
            rubric = None
        return {
            "max_upload_mb": settings.max_upload_mb,
            "demo": transcription.name == "demo" or qa.name == "demo",
            "rubric": rubric_items(rubric) if rubric else [],
            "active_rubric_id": rubric.id if rubric else None,
        }

    @app.get("/dashboard")
    def dashboard(user=Depends(require("review")), db=Depends(get_db)):
        counts = dict(
            db.execute(
                select(Call.status, func.count())
                .where(Call.organization_id == user.organization_id)
                .group_by(Call.status)
            ).all()
        )
        evaluated = db.scalars(
            select(Call).where(Call.organization_id == user.organization_id).options(selectinload(Call.evaluations))
        ).all()
        performance = current_performance(evaluated, db)
        avg = performance["signal_score"]
        recent = db.scalars(
            select(Call)
            .where(Call.organization_id == user.organization_id)
            .options(selectinload(Call.evaluations))
            .order_by(Call.created_at.desc())
            .limit(6)
        ).all()
        return {
            "total": sum(counts.values()),
            "processed": counts.get(Status.COMPLETED, 0),
            "requiring_review": sum(
                1 for c in evaluated if (v := evaluated_view(c, db)) and (v["stale"] or not v["reviewed_at"])
            ),
            "awaiting": sum(counts.get(s, 0) for s in [Status.QUEUED, Status.TRANSCRIBING, Status.ANALYZING]),
            "failed": counts.get(Status.FAILED, 0),
            "average_score": round(avg, 1) if avg is not None else None,
            "performance": performance,
            "recent": [call_view(c, db=db) for c in recent],
        }

    @app.get("/calls")
    def calls(
        q: str = Query(default="", max_length=200),
        status: Status | None = None,
        sort: Literal["newest", "oldest", "name"] = "newest",
        needs_review: bool = False,
        employee_id: str | None = None,
        manager_id: str | None = None,
        flagged: bool = False,
        outdated: bool = False,
        processing: bool = False,
        rubric_id: str | None = None,
        date_from: float | None = Query(None, ge=0),
        date_to: float | None = Query(None, ge=0),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
        user=Depends(require("review")),
        db=Depends(get_db),
    ):
        query = select(Call).where(Call.organization_id == user.organization_id).options(selectinload(Call.evaluations))
        if manager_id:
            query = query.where(manager_filter(db, manager_id, user.organization_id))
        if employee_id:
            if employee_id != "unassigned":
                employee = employee_in_org(db, employee_id, user.organization_id)
                if manager_id and employee.manager_id != (None if manager_id == "unassigned" else manager_id):
                    raise HTTPException(422, "Employee is not a current direct report of the selected manager")
            elif manager_id and manager_id != "unassigned":
                raise HTTPException(422, "Unassigned interactions cannot belong to a manager team")
            query = query.where(
                Call.employee_id.is_(None) if employee_id == "unassigned" else Call.employee_id == employee_id
            )
        if q.strip():
            query = query.where(
                Call.filename.icontains(q.strip(), autoescape=True)
                | Call.id.icontains(q.strip(), autoescape=True)
                | Call.audit_number.icontains(q.strip(), autoescape=True)
            )
        if flagged:
            query = query.where(current_flag_query().exists())
        if processing:
            query = query.where(Call.status.in_([Status.QUEUED, Status.TRANSCRIBING, Status.ANALYZING]))
        if date_from is not None and date_to is not None and date_from >= date_to:
            raise HTTPException(422, "End date must follow start date")
        if date_from is not None:
            query = query.where(Call.created_at >= date_from)
        if date_to is not None:
            query = query.where(Call.created_at < date_to)
        if rubric_id:
            from .models import Rubric

            if (
                db.scalar(
                    select(Rubric.id).where(Rubric.id == rubric_id, Rubric.organization_id == user.organization_id)
                )
                is None
            ):
                raise HTTPException(404, "Scorecard not found")
            latest_rubric = (
                select(Evaluation.rubric_id)
                .where(Evaluation.call_id == Call.id)
                .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
                .limit(1)
                .correlate(Call)
                .scalar_subquery()
            )
            query = query.where(latest_rubric == rubric_id)
        if status:
            query = query.where(Call.status == status)
        if needs_review or outdated:
            latest = (
                select(Evaluation.id)
                .where(Evaluation.call_id == Call.id)
                .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
                .limit(1)
                .correlate(Call)
                .scalar_subquery()
            )
            current_revision = (
                select(func.coalesce(func.max(SpeakerCorrection.id), 0))
                .where(SpeakerCorrection.call_id == Call.id)
                .correlate(Call)
                .scalar_subquery()
            )
            query = query.where(
                select(Evaluation.id)
                .where(
                    Evaluation.id == latest,
                    Evaluation.transcript_revision != current_revision
                    if outdated
                    else or_(Evaluation.reviewed_at.is_(None), Evaluation.transcript_revision != current_revision),
                )
                .exists()
            )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(
            query.order_by(
                {"newest": Call.created_at.desc(), "oldest": Call.created_at.asc(), "name": Call.filename.asc()}[sort],
                Call.id,
            )
            .offset(offset)
            .limit(limit)
        ).all()
        flagged_ids = set(
            db.scalars(select(Call.id).where(Call.id.in_([c.id for c in rows]), current_flag_query().exists()))
        )
        return {"items": [call_view(c, db=db, flagged=c.id in flagged_ids) for c in rows], "total": total}

    @app.post("/calls", status_code=201)
    async def upload(
        file: UploadFile = File(...),
        rubric_id: str | None = Form(None),
        user=Depends(require("review")),
        db=Depends(get_db),
    ):
        call = await ingest(
            file, user, settings, db, transcription.name == "demo" or qa.name == "demo", rubric_id=rubric_id
        )
        event("upload_received", call.id, size_bytes=call.size_bytes)
        return call_view(call)

    def get_call(call_id, db, user):
        call = db.scalar(select(Call).where(Call.id == call_id, Call.organization_id == user.organization_id))
        if not call:
            raise HTTPException(404, "Call not found")
        return call

    @app.get("/calls/{call_id}")
    def detail(call_id: str, user=Depends(require("review")), db=Depends(get_db)):
        return call_view(get_call(call_id, db, user), detail=True, db=db)

    @app.get("/calls/{call_id}/audio")
    def audio(call_id: str, user=Depends(require("review")), db=Depends(get_db)):
        call = get_call(call_id, db, user)
        path = settings.upload_dir / call.storage_name
        if not path.is_file():
            raise HTTPException(404, "Recording is missing from storage")
        return FileResponse(
            path, media_type=call.content_type, filename=call.filename, content_disposition_type="inline"
        )

    @app.post("/calls/{call_id}/retry")
    def retry(call_id: str, user=Depends(require("review")), db=Depends(get_db)):
        get_call(call_id, db, user)
        result = db.execute(
            update(Call)
            .where(Call.id == call_id, Call.organization_id == user.organization_id, Call.status == Status.FAILED)
            .values(status=Status.QUEUED, error=None, failed_stage=None)
        )
        db.commit()
        if result.rowcount != 1:
            raise HTTPException(409, "Only failed calls can be retried")
        event("processing_requeued", call_id)
        return {"status": "queued"}

    return app


logging.basicConfig(level=logging.INFO, format="%(message)s")
