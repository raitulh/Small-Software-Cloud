import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.db.base import Base
from app.db.session import get_db
from app.deps import get_arq_pool, get_current_user
from app.main import app
from app.models import Membership, MembershipRole, Organization, Project, Service, User
from app.security import hash_password

class DummyPool:
    def __init__(self):
        self.jobs = []
    async def enqueue_job(self, fn, *args, **kwargs):
        self.jobs.append((fn, args))

@pytest.fixture
async def test_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Create test user, org, membership, project, and service
        user = User(email="dev@example.com", password_hash=hash_password("Password123!"))
        org = Organization(name="Acme Inc", slug="acme")
        session.add_all([user, org])
        await session.flush()

        membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER)
        project = Project(organization_id=org.id, name="Backend API", slug="backend-api")
        session.add_all([membership, project])
        await session.flush()

        service = Service(project_id=project.id, name="Web App", slug="web-app", deploy_token="test-secret-token-123")
        session.add(service)
        await session.commit()

        yield {
            "session_factory": session_factory,
            "user": user,
            "org": org,
            "project": project,
            "service": service
        }

    await engine.dispose()

@pytest.mark.asyncio
async def test_raw_env_import_and_secrets(test_env):
    user = test_env["user"]
    service = test_env["service"]
    session_factory = test_env["session_factory"]

    async def override_get_db():
        async with session_factory() as s:
            yield s

    async def override_get_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            raw_content = (
                "# Application config\n"
                "PORT=8080\n"
                "DATABASE_URL=postgres://user:pass@localhost:5432/db\n"
                "JWT_SECRET_KEY='super-secret-key'\n"
                "APP_NAME=\"Small Cloud App\"\n"
            )
            response = await client.post(
                f"/v1/services/{service.id}/env/raw",
                json={"raw_env": raw_content, "merge": False}
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 4

            # Verify auto-detection of secrets
            by_key = {item["key"]: item for item in data}
            assert by_key["PORT"]["value"] == "8080"
            assert by_key["PORT"]["is_secret"] is False
            assert by_key["JWT_SECRET_KEY"]["value"] == "super-secret-key"
            assert by_key["JWT_SECRET_KEY"]["is_secret"] is True
            assert by_key["APP_NAME"]["value"] == "Small Cloud App"
    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_deploy_hook_execution(test_env):
    service = test_env["service"]
    session_factory = test_env["session_factory"]
    dummy_pool = DummyPool()

    async def override_get_db():
        async with session_factory() as s:
            yield s

    def override_get_pool():
        return dummy_pool

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = override_get_pool

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Calling without token fails with 401
            res_fail = await client.post(f"/v1/services/{service.id}/deploy-hook")
            assert res_fail.status_code == 401

            # 2. Calling with query token succeeds with 202 Accepted
            res_query = await client.post(f"/v1/services/{service.id}/deploy-hook?token=test-secret-token-123")
            assert res_query.status_code == 202
            data = res_query.json()
            assert data["status"] == "queued"
            assert len(dummy_pool.jobs) == 1

            # 3. Calling with Bearer token header also succeeds
            res_header = await client.post(
                f"/v1/services/{service.id}/deploy-hook",
                headers={"Authorization": "Bearer test-secret-token-123"}
            )
            assert res_header.status_code == 202
            assert len(dummy_pool.jobs) == 2
    finally:
        app.dependency_overrides.clear()
