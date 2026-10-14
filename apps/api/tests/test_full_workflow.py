import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.db.base import Base
from app.db.session import get_db
from app.deps import get_arq_pool
from app.main import app

class MockArqPool:
    def __init__(self):
        self.jobs = []
    async def enqueue_job(self, fn, *args, **kwargs):
        self.jobs.append((fn, args, kwargs))

@pytest.fixture
async def workflow_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()

@pytest.mark.asyncio
async def test_complete_platform_lifecycle_workflow(workflow_db):
    mock_pool = MockArqPool()

    async def override_get_db():
        async with workflow_db() as s:
            yield s

    def override_get_pool():
        return mock_pool

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = override_get_pool

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Register a new user
            reg_res = await client.post(
                "/v1/auth/register",
                json={
                    "email": "lead-dev@smallcloud.internal",
                    "password": "StrongPassword123!",
                    "organization_name": "Starlight Labs"
                }
            )
            assert reg_res.status_code == 201, reg_res.text
            reg_data = reg_res.json()
            assert "access_token" in reg_data
            assert reg_data["user"]["email"] == "lead-dev@smallcloud.internal"
            token = reg_data["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # 2. Login to verify authentication flow
            login_res = await client.post(
                "/v1/auth/login",
                json={"email": "lead-dev@smallcloud.internal", "password": "StrongPassword123!"}
            )
            assert login_res.status_code == 200
            assert login_res.json()["access_token"] is not None

            # 3. View Organizations
            orgs_res = await client.get("/v1/organizations", headers=headers)
            assert orgs_res.status_code == 200
            orgs = orgs_res.json()
            assert len(orgs) == 1
            org_id = orgs[0]["id"]
            assert orgs[0]["name"] == "Starlight Labs"

            # 4. View Dashboard Overview
            dash_res = await client.get(f"/v1/dashboard/overview?organization_id={org_id}", headers=headers)
            assert dash_res.status_code == 200
            dash_data = dash_res.json()
            assert dash_data["organization"]["id"] == org_id
            assert dash_data["projects"] == []
            assert dash_data["usage"]["projects"] == 0

            # 5. Create a Project
            proj_res = await client.post(
                "/v1/projects",
                headers=headers,
                json={
                    "name": "E-Commerce Gateway",
                    "slug": "ecom-gateway",
                    "description": "Core payment and checkout microservice",
                    "organization_id": org_id
                }
            )
            assert proj_res.status_code == 201, proj_res.text
            project = proj_res.json()
            project_id = project["id"]
            assert project["name"] == "E-Commerce Gateway"
            assert project["slug"] == "ecom-gateway"

            # 6. Update Project Details
            patch_proj = await client.patch(
                f"/v1/projects/{project_id}",
                headers=headers,
                json={"description": "Updated description for checkout service"}
            )
            assert patch_proj.status_code == 200
            assert patch_proj.json()["description"] == "Updated description for checkout service"

            # 7. Create a Service inside the Project
            svc_res = await client.post(
                f"/v1/projects/{project_id}/services",
                headers=headers,
                json={
                    "name": "Cart API",
                    "slug": "cart-api",
                    "kind": "web",
                    "runtime": "python",
                    "source_repo": "https://github.com/example/cart-service",
                    "branch": "main",
                    "internal_port": 8000,
                    "memory_mb": 256,
                    "cpu_millicores": 250
                }
            )
            assert svc_res.status_code == 201, svc_res.text
            service = svc_res.json()
            service_id = service["id"]
            assert service["name"] == "Cart API"
            assert service["slug"] == "cart-api"

            # 8. Configure Environment Variables
            env_res = await client.put(
                f"/v1/services/{service_id}/env",
                headers=headers,
                json={
                    "variables": [
                        {"key": "DB_URL", "value": "postgres://user:pass@db:5432/cart", "is_secret": False},
                        {"key": "STRIPE_API_KEY", "value": "sk_test_secret_key_123", "is_secret": True}
                    ]
                }
            )
            assert env_res.status_code == 200
            vars_data = env_res.json()
            assert len(vars_data) == 2

            # 9. Verify Masking in GET env
            get_env_masked = await client.get(f"/v1/services/{service_id}/env?reveal=false", headers=headers)
            assert get_env_masked.status_code == 200
            masked_by_key = {item["key"]: item for item in get_env_masked.json()}
            assert masked_by_key["STRIPE_API_KEY"]["value"] == "••••••••"

            get_env_revealed = await client.get(f"/v1/services/{service_id}/env?reveal=true", headers=headers)
            assert get_env_revealed.status_code == 200
            revealed_by_key = {item["key"]: item for item in get_env_revealed.json()}
            assert revealed_by_key["STRIPE_API_KEY"]["value"] == "sk_test_secret_key_123"

            # 10. Generate Deploy Token for CI/CD
            token_res = await client.post(f"/v1/services/{service_id}/deploy-token", headers=headers)
            assert token_res.status_code == 200
            token_data = token_res.json()
            deploy_token = token_data.get("deploy_token")
            assert deploy_token is not None

            # 11. Trigger Deploy Hook via Webhook
            hook_res = await client.post(f"/v1/services/{service_id}/deploy-hook?token={deploy_token}")
            assert hook_res.status_code == 202
            deployment = hook_res.json()
            deployment_id = deployment["id"]
            assert deployment["status"] == "queued"

            # 12. Cancel the Deployment
            cancel_res = await client.post(f"/v1/deployments/{deployment_id}/cancel", headers=headers)
            assert cancel_res.status_code == 200
            assert cancel_res.json()["status"] == "canceled"

            # 13. Verify Dashboard Overview reflection
            updated_dash = await client.get(f"/v1/dashboard/overview?organization_id={org_id}", headers=headers)
            assert updated_dash.status_code == 200
            overview = updated_dash.json()
            assert overview["usage"]["projects"] == 1
            assert overview["usage"]["services"] == 1

            # 14. Clean up Service and Project
            del_svc = await client.delete(f"/v1/services/{service_id}", headers=headers)
            assert del_svc.status_code == 204

            del_proj = await client.delete(f"/v1/projects/{project_id}", headers=headers)
            assert del_proj.status_code == 204
    finally:
        app.dependency_overrides.clear()
