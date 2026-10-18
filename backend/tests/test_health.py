import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "NeoHelp" in data["app"]
        assert data["health"] == "/api/health"

@pytest.mark.asyncio
async def test_ping_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health/ping")
        assert response.status_code == 200
        assert response.json() == {"status": "pong"}
