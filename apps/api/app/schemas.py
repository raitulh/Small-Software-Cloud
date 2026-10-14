import re
import uuid
from datetime import datetime
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.models import DeploymentStatus, RuntimeKind, ServiceKind

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    organization_name: str | None = Field(default=None, min_length=2, max_length=120)

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    created_at: datetime

class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead

class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    role: str | None = None
    created_at: datetime

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=64)

class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    email: EmailStr | None = None
    created_at: datetime

class ProjectCreate(BaseModel):
    organization_id: uuid.UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=64)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")

    @classmethod
    def name_trimmed(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Project name must contain at least two non-space characters")
        return value

    @field_validator("slug")
    @classmethod
    def slug_valid(cls, value):
        if value is not None and not SLUG_RE.fullmatch(value):
            raise ValueError("Slug may contain lowercase letters, numbers and hyphens")
        return value

class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime

class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def name_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Project name must contain at least two non-space characters")
        return value


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=64)
    kind: ServiceKind = ServiceKind.WEB
    runtime: RuntimeKind = RuntimeKind.PYTHON
    source_repo: str | None = Field(default=None, max_length=500)
    branch: str = Field(default="main", min_length=1, max_length=160)
    image_ref: str | None = Field(default=None, max_length=500)
    internal_port: int = Field(default=8000, ge=1, le=65535)
    memory_mb: int | None = Field(default=None, ge=64, le=65536)
    cpu_millicores: int | None = Field(default=None, ge=50, le=64000)

    @field_validator("name")
    @classmethod
    def name_trimmed(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Service name must contain at least two non-space characters")
        return value

    @field_validator("slug")
    @classmethod
    def slug_valid(cls, value):
        if value is not None and not SLUG_RE.fullmatch(value):
            raise ValueError("Slug may contain lowercase letters, numbers and hyphens")
        return value

    @field_validator("source_repo")
    @classmethod
    def repo_url_valid(cls, value):
        if value is None or value == "":
            return None
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "gitlab.com", "codeberg.org"}:
            raise ValueError("Repository URL must use HTTPS and a supported public Git host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Repository URL must not contain credentials, query parameters or fragments")
        return value.rstrip("/")

    @field_validator("image_ref")
    @classmethod
    def image_ref_valid(cls, value):
        if value is None or value == "":
            return None
        if value.startswith("-") or any(c.isspace() for c in value):
            raise ValueError("Invalid container image reference")
        if "@" in value and not value.split("@", 1)[1].startswith("sha256:"):
            raise ValueError("Digest references must use sha256")
        return value

class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    slug: str
    kind: ServiceKind
    runtime: RuntimeKind
    source_repo: str | None
    branch: str
    image_ref: str | None
    internal_port: int
    memory_mb: int
    cpu_millicores: int
    current_deployment_id: uuid.UUID | None
    deploy_token: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    branch: str | None = Field(default=None, min_length=1, max_length=160)
    source_repo: str | None = Field(default=None, max_length=500)
    image_ref: str | None = Field(default=None, max_length=500)
    internal_port: int | None = Field(default=None, ge=1, le=65535)
    memory_mb: int | None = Field(default=None, ge=64, le=65536)
    cpu_millicores: int | None = Field(default=None, ge=50, le=64000)

    @field_validator("name")
    @classmethod
    def name_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Service name must contain at least two non-space characters")
        return value

    @field_validator("source_repo")
    @classmethod
    def repo_url_valid(cls, value):
        if value is None or value == "":
            return None
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "gitlab.com", "codeberg.org"}:
            raise ValueError("Repository URL must use HTTPS and a supported public Git host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Repository URL must not contain credentials, query parameters or fragments")
        return value.rstrip("/")

class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    service_id: uuid.UUID
    status: DeploymentStatus
    commit_sha: str | None
    image_digest: str | None
    output_url: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

class DeploymentLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    deployment_id: uuid.UUID
    level: str
    message: str
    created_at: datetime

class UsageSummary(BaseModel):
    projects: int
    services: int
    deployments_last_30_days: int
    configured_memory_mb: int
    configured_cpu_millicores: int
    deployment_driver: str

class EnvVarItem(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: str
    is_secret: bool = False

class EnvVarBulkUpdate(BaseModel):
    variables: list[EnvVarItem]

class EnvVarRawImport(BaseModel):
    raw_env: str = Field(description="Raw .env string content")
    merge: bool = Field(default=False, description="If True, merges with existing vars instead of full replace")

class EnvVarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    value: str
    is_secret: bool

class ServiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    slug: str
    kind: ServiceKind
    runtime: RuntimeKind
    source_repo: str | None
    branch: str
    image_ref: str | None
    internal_port: int
    memory_mb: int
    cpu_millicores: int
    deploy_token: str | None = None
    status: str
    latest_deployment: DeploymentRead | None = None
    created_at: datetime
    updated_at: datetime


class ProjectWithServices(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    services: list[ServiceSummary] = []

class DashboardOverview(BaseModel):
    organization: OrganizationRead
    projects: list[ProjectWithServices]
    usage: UsageSummary
    recent_deployments: list[DeploymentRead]

