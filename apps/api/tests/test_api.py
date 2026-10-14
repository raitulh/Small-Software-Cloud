import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "0.2.0"
        assert data["deployment_driver"] == "mock"

@pytest.mark.asyncio
async def test_health_live_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

@pytest.mark.asyncio
async def test_unauthorized_access():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/projects")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired access token"

@pytest.mark.asyncio
async def test_dashboard_unauthorized():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/dashboard/overview")
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_organizations_unauthorized():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/organizations")
        assert response.status_code == 401
