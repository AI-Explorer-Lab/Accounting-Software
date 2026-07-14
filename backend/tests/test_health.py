import httpx
import pytest

from constant.values import REQUEST_ID_HEADER
from main import app


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"
    assert response.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_scaffold_endpoint_uses_local_identity() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/scaffold", headers={"X-User-ID": "tester"}
        )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "name": "architecture",
        "status": "scaffold-ready",
        "actor": "tester",
    }
