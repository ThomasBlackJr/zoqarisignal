import time
import uuid
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    REVIEWER = "REVIEWER"
    EMPLOYEE = "EMPLOYEE"
    SUPERVISOR = "SUPERVISOR"


class Status(StrEnum):
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


def identifier():
    return str(uuid.uuid4())


LEGACY_ORG = "00000000-0000-0000-0000-000000000002"


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    subscription_status: Mapped[str] = mapped_column(String(20), default="inactive")
    entitlement_source: Mapped[str | None] = mapped_column(String(30))
    entitlement_expires_at: Mapped[float | None] = mapped_column(Float)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(30), default=Role.SUPERVISOR)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    organization: Mapped[Organization | None] = relationship()
    calls: Mapped[list["Call"]] = relationship(back_populates="uploader")


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True)
    user: Mapped[User] = relationship()


class AccountToken(Base):
    __tablename__ = "account_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[float] = mapped_column(Float, index=True)


class EntitlementEvent(Base):
    __tablename__ = "entitlement_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    expires_at: Mapped[float] = mapped_column(Float)


class Call(Base):
    __tablename__ = "calls"
    audit_number: Mapped[str | None] = mapped_column(String(30), unique=True, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    filename: Mapped[str] = mapped_column(String(255))
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), index=True)
    assignment_revision: Mapped[int] = mapped_column(Integer, default=0)
    employee: Mapped["Employee | None"] = relationship()
    requested_transcript_context: Mapped[dict | None] = mapped_column(JSON)
    storage_name: Mapped[str] = mapped_column(String(50), unique=True)
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    status: Mapped[str] = mapped_column(String(30), default=Status.QUEUED, index=True)
    error: Mapped[str | None] = mapped_column(Text)
    failed_stage: Mapped[str | None] = mapped_column(String(30))
    requested_rubric_id: Mapped[str | None] = mapped_column(String(36))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    uploader: Mapped[User] = relationship(back_populates="calls")
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="call", cascade="all, delete-orphan", uselist=False
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="call", cascade="all, delete-orphan", order_by="(Evaluation.created_at, Evaluation.id)"
    )

    @property
    def evaluation(self):
        return self.evaluations[-1] if self.evaluations else None


class Transcript(Base):
    __tablename__ = "transcripts"
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    segments: Mapped[list] = mapped_column(JSON)
    # Presentation-only cache. Original text/segments remain the source of truth.
    conversation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    call: Mapped[Call] = relationship(back_populates="transcript")


class Evaluation(Base):
    __tablename__ = "qa_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    rubric_id: Mapped[str | None] = mapped_column(ForeignKey("rubrics.id"))
    overall_score: Mapped[int] = mapped_column(Integer)
    transcript_revision: Mapped[int] = mapped_column(Integer, default=0)
    transcript_context: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    rubric_version: Mapped[str] = mapped_column(String(30))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    call: Mapped[Call] = relationship(back_populates="evaluations")
    rubric: Mapped["Rubric | None"] = relationship()
    adjustments: Mapped[list["ScoreAdjustment"]] = relationship(order_by="ScoreAdjustment.id")
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[float | None] = mapped_column(Float)


class Rubric(Base):
    __tablename__ = "rubrics"
    __table_args__ = (UniqueConstraint("organization_id", "version", name="uq_rubric_org_version"),)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    activated_at: Mapped[float | None] = mapped_column(Float)
    categories: Mapped[list["RubricCategory"]] = relationship(
        cascade="all, delete-orphan", order_by="RubricCategory.display_order"
    )


class RubricCategory(Base):
    __tablename__ = "rubric_categories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer)


class SpeakerCorrection(Base):
    __tablename__ = "speaker_corrections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    source_start: Mapped[int] = mapped_column(Integer)
    source_end: Mapped[int] = mapped_column(Integer)
    speaker_id: Mapped[str | None] = mapped_column(Text)
    inferred_role: Mapped[str] = mapped_column(String(20))
    previous_role: Mapped[str] = mapped_column(String(20))
    corrected_role: Mapped[str | None] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(20))
    corrected_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    corrected_at: Mapped[float] = mapped_column(Float, default=time.time)
    actor: Mapped[User] = relationship()


class ScoreAdjustment(Base):
    __tablename__ = "score_adjustments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("qa_evaluations.id"), index=True)
    category_key: Mapped[str] = mapped_column(String(80))
    score: Mapped[int | None] = mapped_column(Integer)
    previous_score: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[float] = mapped_column(Float, default=time.time)
    actor: Mapped[User] = relationship()


class UploadBatch(Base):
    __tablename__ = "upload_batches"
    rubric_id: Mapped[str | None] = mapped_column(ForeignKey("rubrics.id"))
    rubric: Mapped["Rubric | None"] = relationship()
    __table_args__ = (UniqueConstraint("organization_id", "request_key", name="uq_batch_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    request_key: Mapped[str] = mapped_column(String(64))
    manifest_hash: Mapped[str] = mapped_column(String(64))
    items: Mapped[list["UploadItem"]] = relationship(order_by="UploadItem.position")


class UploadItem(Base):
    __tablename__ = "upload_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    batch_id: Mapped[str] = mapped_column(ForeignKey("upload_batches.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id"), index=True)
    duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    call: Mapped["Call | None"] = relationship()


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("organization_id", "external_id", name="uq_employee_external"),
        UniqueConstraint("organization_id", "email", name="uq_employee_email"),
    )
    external_id: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254))
    manager_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    manager_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), index=True)
    linked_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), unique=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(120), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class EmployeeAssignment(Base):
    __tablename__ = "employee_assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    previous_employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    changed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[float] = mapped_column(Float, default=time.time)
    actor: Mapped[User] = relationship()
    employee: Mapped["Employee | None"] = relationship(foreign_keys=[employee_id])
    previous_employee: Mapped["Employee | None"] = relationship(foreign_keys=[previous_employee_id])


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    invited_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    expires_at: Mapped[float] = mapped_column(Float)
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[float | None] = mapped_column(Float)


class UserPreference(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    appearance: Mapped[str] = mapped_column(String(10), default="system")
    modules: Mapped[list] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class EmployeeHierarchyChange(Base):
    __tablename__ = "employee_hierarchy_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    previous_manager_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    manager_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    previous_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[float] = mapped_column(Float, default=time.time)


class AdminEvent(Base):
    __tablename__ = "admin_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    resource_type: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class PendingAudioDeletion(Base):
    __tablename__ = "pending_audio_deletions"
    call_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    storage_name: Mapped[str] = mapped_column(String(50))
    event_id: Mapped[str] = mapped_column(ForeignKey("admin_events.id"))


class CoachingDraft(Base):
    __tablename__ = "coaching_drafts"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    choice: Mapped[dict] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class AuditSequence(Base):
    __tablename__ = "audit_sequence"
    __table_args__ = {"sqlite_autoincrement": True}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class FlagRule(Base):
    __tablename__ = "flag_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    phrase: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    severity: Mapped[str] = mapped_column(String(20), default="attention")
    notify: Mapped[bool] = mapped_column(Boolean, default=False)
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class FlagDetection(Base):
    __tablename__ = "flag_detections"
    __table_args__ = (
        UniqueConstraint("call_id", "rule_id", "rule_revision", "transcript_revision", name="uq_flag_detection"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("flag_rules.id"))
    rule_revision: Mapped[int] = mapped_column(Integer)
    transcript_revision: Mapped[int] = mapped_column(Integer)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    phrase: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20))
    matches: Mapped[list] = mapped_column(JSON)
    match_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class FlagNotification(Base):
    __tablename__ = "flag_notifications"
    __table_args__ = (UniqueConstraint("detection_id", "recipient_id", name="uq_flag_recipient"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    detection_id: Mapped[str] = mapped_column(ForeignKey("flag_detections.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    attempted_at: Mapped[float | None] = mapped_column(Float)


class VerificationCode(Base):
    __tablename__ = "verification_codes"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    challenge_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[float] = mapped_column(Float)
    sent_at: Mapped[float] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class BillingAccount(Base):
    __tablename__ = "billing_accounts"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    subscription_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    checkout_id: Mapped[str | None] = mapped_column(String(100))
    checkout_key: Mapped[str | None] = mapped_column(String(36))
    checkout_expires: Mapped[float | None] = mapped_column(Float)
    checkout_plan: Mapped[str | None] = mapped_column(String(40))
    plan: Mapped[str | None] = mapped_column(String(30))
    interval: Mapped[str | None] = mapped_column(String(10))
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    livemode: Mapped[bool] = mapped_column(Boolean, default=False)
    synced_at: Mapped[float | None] = mapped_column(Float)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class EmployeeImport(Base):
    __tablename__ = "employee_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    rows: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[float] = mapped_column(Float)
    committed_at: Mapped[float | None] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer, default=0)
