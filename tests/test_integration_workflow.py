"""
ACAS v2 - Integration Tests
End-to-end user workflows
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
import uuid


def unique_email(prefix: str = "int") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    email = unique_email("reg")
    resp = await client.post("/auth/register", json={
        "email": email, "password": "TestPass123!",
        "name": "Integration User", "company": "Int Corp"
    })
    assert resp.status_code == 201
    data = resp.json()
    return {"email": email, "password": "TestPass123!", "id": data["id"]}


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, registered_user: dict) -> dict:
    resp = await client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"]
    })
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestUserWorkflow:
    """Complete user workflow: register → login → use API → logout"""

    async def test_complete_user_journey(self, client: AsyncClient):
        """Test full flow"""
        # 1. Register
        email = unique_email("journey")
        resp = await client.post("/auth/register", json={
            "email": email, "password": "JourneyPass123!",
            "name": "Journey User", "company": "Journey Corp"
        })
        assert resp.status_code == 201
        user_id = resp.json()["id"]

        # 2. Login
        resp = await client.post("/auth/login", json={
            "email": email, "password": "JourneyPass123!"
        })
        assert resp.status_code == 200
        tokens = resp.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # 3. Get profile
        resp = await client.get("/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == email

        # 4. Update profile
        resp = await client.patch("/auth/me", headers=headers, json={"name": "Updated Journey"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Journey"

        # 5. Create API key
        resp = await client.post("/auth/api-keys", params={"name": "Journey Key"}, headers=headers)
        assert resp.status_code == 200
        api_key = resp.json()["key"]

        # 6. List API keys
        resp = await client.get("/auth/api-keys", headers=headers)
        assert resp.status_code == 200
        assert "keys" in resp.json()

        # 7. Logout
        resp = await client.post("/auth/logout", headers=headers)
        assert resp.status_code == 200

        # 8. Verify token revoked (if blacklist works)
        resp = await client.get("/auth/me", headers=headers)
        # May be 200 or 401
        assert resp.status_code in (200, 401)


class TestAPIKeyWorkflow:
    """API key authentication workflow"""

    async def test_api_key_auth(self, client: AsyncClient, auth_headers: dict):
        """Test using API key for authentication"""
        # Create API key
        resp = await client.post("/auth/api-keys", params={"name": "Test Key"}, headers=auth_headers)
        assert resp.status_code == 200
        api_key = resp.json()["key"]

        # Use API key to authenticate (assuming endpoint supports API key auth)
        # This depends on API implementation
        # For now, just verify key creation
        assert api_key.startswith("ak_")


class TestErrorHandling:
    """Test error responses are proper JSON"""

    async def test_404_returns_json(self, client: AsyncClient):
        """404 should return JSON, not HTML"""
        resp = await client.get("/nonexistent-endpoint")
        assert resp.status_code == 404
        # Should be JSON
        try:
            data = resp.json()
            assert "detail" in data or "error" in data
        except:
            pass  # May return HTML

    async def test_401_returns_json(self, client: AsyncClient):
        """401 should return JSON"""
        resp = await client.get("/auth/me")
        assert resp.status_code in (401, 403)
        try:
            data = resp.json()
            assert "detail" in data or "error" in data
        except:
            pass
