"""SQLAlchemy 2.x models. Persistent store = Neon PostgreSQL (+ pgvector)."""
import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.dbtypes import EmbeddingType


def _now() -> datetime:
    return datetime.now(timezone.utc)


def pk():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def ts():
    return mapped_column(DateTime(timezone=True), default=_now)


class Role(str, enum.Enum):
    admin = "admin"
    advocate = "advocate"
    legal_assistant = "legal_assistant"


# ------------------------------------------------------------------ tenancy / users
class Organisation(Base):
    __tablename__ = "organisations"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)  # invite/join code
    created_at: Mapped[datetime] = ts()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32), default=Role.advocate.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump = revoke all tokens (logout)
    bar_council_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = ts()


# ------------------------------------------------------------------ cases
class Case(Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_type: Mapped[str | None] = mapped_column(String(100), nullable=True)  # civil|criminal|tenancy|employment|...
    jurisdiction: Mapped[str | None] = mapped_column(String(200), nullable=True)
    forum: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")  # open|archived
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CaseMember(Base):  # explicit sharing within the same organisation
    __tablename__ = "case_members"
    __table_args__ = (UniqueConstraint("case_id", "user_id"),)
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    access: Mapped[str] = mapped_column(String(16), default="editor")  # viewer|editor
    created_at: Mapped[datetime] = ts()


class Party(Base):
    __tablename__ = "parties"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(100))  # complainant, accused, landlord, tenant, ...
    relationship_to: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual|extracted
    created_at: Mapped[datetime] = ts()


class Fact(Base):
    __tablename__ = "facts"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    disputed: Mapped[bool] = mapped_column(Boolean, default=False)
    fact_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = ts()


class LegalIssue(Base):
    __tablename__ = "legal_issues"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    created_at: Mapped[datetime] = ts()


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(64), default="document")  # document|witness|digital|physical|expert
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="held")  # held|requested|missing
    issue_ids: Mapped[list | None] = mapped_column(JSON, default=list)  # evidence -> issue/argument mapping
    fact_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    supports: Mapped[str] = mapped_column(String(16), default="supports")  # supports|undermines|neutral
    created_at: Mapped[datetime] = ts()


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(16), default="task")  # task|deadline|limitation
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    trigger_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # limitation: advocate-entered
    period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # limitation: advocate-entered
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    reviewed: Mapped[bool] = mapped_column(Boolean, default=True)  # extracted deadlines start unreviewed
    created_at: Mapped[datetime] = ts()


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = ts()


class CaseTwinVersion(Base):
    __tablename__ = "case_twin_versions"
    __table_args__ = (UniqueConstraint("case_id", "version"),)
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = ts()


# ------------------------------------------------------------------ documents
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    uploader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_type_source: Mapped[str] = mapped_column(String(16), default="user")  # user|classifier
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    version_group: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # uploaded -> processing -> extracted | extracted_mock_ocr | needs_ocr | failed
    processing_status: Mapped[str] = mapped_column(String(32), default="uploaded")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|reviewed
    created_at: Mapped[datetime] = ts()


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_no"),)
    id: Mapped[uuid.UUID] = pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    ocr: Mapped[bool] = mapped_column(Boolean, default=False)


class Extraction(Base):
    """Every extracted fact keeps document + page provenance and a source label."""
    __tablename__ = "extractions"
    id: Mapped[uuid.UUID] = pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # party|date|deadline|amount|clause|obligation|legal_ref|duration|missing|risk
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), default="explicit")  # explicit (in document) | ai_inferred
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|confirmed|rejected|edited
    edited_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = ts()


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_no: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(EmbeddingType, nullable=True)


# ------------------------------------------------------------------ legal knowledge
class LegalSource(Base):
    """Source registry: where legal material comes from, whether access is permitted, and ingestion state."""
    __tablename__ = "legal_sources"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(300))
    layer: Mapped[str] = mapped_column(String(40), index=True)  # one of the 12 coverage layers
    jurisdiction: Mapped[str] = mapped_column(String(120), index=True, default="India")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    access_method: Mapped[str] = mapped_column(String(24), default="manual")  # api|download|scrape|manual
    access_status: Mapped[str] = mapped_column(String(32), default="unverified")  # unverified|permitted|restricted|blocked
    licence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_status: Mapped[str] = mapped_column(String(24), default="not_started")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = ts()


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id: Mapped[uuid.UUID] = pk()
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("legal_sources.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24))  # manual_upload|seed|monitor
    status: Mapped[str] = mapped_column(String(24), default="running")
    instruments_added: Mapped[int] = mapped_column(Integer, default=0)
    chunks_added: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = ts()


class LegalInstrument(Base):
    __tablename__ = "legal_instruments"
    id: Mapped[uuid.UUID] = pk()
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("legal_sources.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(400))
    instrument_type: Mapped[str] = mapped_column(String(40), index=True)  # constitution|act|rule|notification|judgment|circular|bylaw|treaty|secondary
    authority_class: Mapped[str] = mapped_column(String(16), default="primary")  # primary|secondary
    jurisdiction: Mapped[str] = mapped_column(String(120), index=True, default="India")
    court: Mapped[str | None] = mapped_column(String(200), nullable=True)
    citation: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instrument_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # enactment / judgment date
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)  # commencement
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)  # repeal / supersession
    status: Mapped[str] = mapped_column(String(16), default="in_force")  # in_force|repealed|amended|historical
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    amendments: Mapped[list | None] = mapped_column(JSON, default=list)
    tags: Mapped[dict | None] = mapped_column(JSON, default=dict)  # e.g. {"offences": [...], "stance": "..."}
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified")  # unverified|human_verified|synthetic_test
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = ts()


class LegalChunk(Base):
    __tablename__ = "legal_chunks"
    id: Mapped[uuid.UUID] = pk()
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_instruments.id", ondelete="CASCADE"), index=True)
    chunk_no: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(120), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(EmbeddingType, nullable=True)


# ------------------------------------------------------------------ chat / voice
class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = ts()


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant
    content: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(8), default="text")  # text|voice
    citations: Mapped[list | None] = mapped_column(JSON, default=list)
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)  # mode, coverage, flags
    created_at: Mapped[datetime] = ts()


# ------------------------------------------------------------------ agents / reports
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(24))  # case_assessment|criminal_intelligence
    status: Mapped[str] = mapped_column(String(24), default="running")  # running|awaiting_review|approved|rejected|failed
    mode: Mapped[str] = mapped_column(String(8), default="mock")  # mock|live
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16))  # ok|retrying|failed|skipped
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = ts()


class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoints"
    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    after_node: Mapped[str] = mapped_column(String(48))
    state: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = ts()


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(24))  # case_assessment|criminal_intelligence|research
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[dict] = mapped_column(JSON)
    markdown: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|approved|rejected
    mode: Mapped[str] = mapped_column(String(8), default="mock")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = ts()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_created", "org_id", "created_at"),)
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = ts()
