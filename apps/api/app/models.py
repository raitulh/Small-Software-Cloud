import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"

class ServiceKind(str, enum.Enum):
    WEB = "web"
    WORKER = "worker"
    CRON = "cron"

class RuntimeKind(str, enum.Enum):
    PYTHON = "python"
    NODE = "node"
    DOCKER_IMAGE = "docker_image"

class DeploymentStatus(str, enum.Enum):
    QUEUED = "queued"
    BUILDING = "building"
    STARTING = "starting"
    HEALTHY = "healthy"
    FAILED = "failed"
    CANCELED = "canceled"

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), default="hobby", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[MembershipRole] = mapped_column(Enum(MembershipRole, name="membership_role", values_callable=lambda e: [x.name for x in e]), default=MembershipRole.OWNER, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"), Index("ix_projects_org_created", "organization_id", "created_at"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class Service(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_services_project_slug"), Index("ix_services_project_created", "project_id", "created_at"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[ServiceKind] = mapped_column(Enum(ServiceKind, name="service_kind", values_callable=lambda e: [x.name for x in e]), default=ServiceKind.WEB, nullable=False)
    runtime: Mapped[RuntimeKind] = mapped_column(Enum(RuntimeKind, name="runtime_kind", values_callable=lambda e: [x.name for x in e]), default=RuntimeKind.PYTHON, nullable=False)
    source_repo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    branch: Mapped[str] = mapped_column(String(160), default="main", nullable=False)
    image_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    internal_port: Mapped[int] = mapped_column(Integer, default=8000, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, default=256, nullable=False)
    cpu_millicores: Mapped[int] = mapped_column(Integer, default=250, nullable=False)
    current_deployment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    deploy_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="created", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (Index("ix_deployments_service_created", "service_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(Enum(DeploymentStatus, name="deployment_status", values_callable=lambda e: [x.name for x in e]), default=DeploymentStatus.QUEUED, nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(80), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class DeploymentLog(Base):
    __tablename__ = "deployment_logs"
    __table_args__ = (Index("ix_deployment_logs_deployment_created", "deployment_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("deployments.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(12), default="INFO", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_org_created", "organization_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_org_metric_time", "organization_id", "metric", "period_start"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class ServiceEnvVar(Base):
    __tablename__ = "service_env_vars"
    __table_args__ = (UniqueConstraint("service_id", "key", name="uq_service_env_var_key"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_status_created", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
