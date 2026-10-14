import uuid
import pytest
from pydantic import ValidationError
from app.schemas import (
    EnvVarBulkUpdate,
    EnvVarItem,
    OrganizationCreate,
    ProjectCreate,
    ProjectUpdate,
    ServiceCreate,
    ServiceUpdate,
)

def test_slug_rejects_spaces():
    with pytest.raises(ValidationError):
        ProjectCreate(name="My Project", slug="My Project")

def test_repository_requires_https_and_allowed_host():
    with pytest.raises(ValidationError):
        ServiceCreate(name="API", runtime="python", source_repo="http://github.com/acme/api")
    with pytest.raises(ValidationError):
        ServiceCreate(name="API", runtime="python", source_repo="https://evil.example/acme/api")

def test_supported_github_repository_accepted():
    payload = ServiceCreate(name="API", runtime="python", source_repo="https://github.com/acme/api")
    assert payload.source_repo == "https://github.com/acme/api"

def test_invalid_image_digest_rejected():
    with pytest.raises(ValidationError):
        ServiceCreate(name="Container", runtime="docker_image", image_ref="ghcr.io/acme/app@sha512:nope")

def test_project_create_with_org_id():
    org_id = uuid.uuid4()
    p = ProjectCreate(name="New Service", organization_id=org_id)
    assert p.organization_id == org_id
    assert p.name == "New Service"

def test_project_update_validation():
    with pytest.raises(ValidationError):
        ProjectUpdate(name="   ")
    valid = ProjectUpdate(name="Updated Name", description="New description")
    assert valid.name == "Updated Name"
    assert valid.description == "New description"

def test_service_update_validation():
    with pytest.raises(ValidationError):
        ServiceUpdate(name=" ")
    with pytest.raises(ValidationError):
        ServiceUpdate(source_repo="http://insecure.example.com")
    valid = ServiceUpdate(name="Worker", internal_port=9000, memory_mb=512)
    assert valid.internal_port == 9000
    assert valid.memory_mb == 512

def test_env_var_bulk_update():
    payload = EnvVarBulkUpdate(variables=[
        EnvVarItem(key="DATABASE_URL", value="postgres://...", is_secret=True),
        EnvVarItem(key="PORT", value="8080", is_secret=False)
    ])
    assert len(payload.variables) == 2
    assert payload.variables[0].is_secret is True

def test_organization_create_validation():
    with pytest.raises(ValidationError):
        OrganizationCreate(name="X")
    org = OrganizationCreate(name="Acme Corp", slug="acme-corp")
    assert org.slug == "acme-corp"
