"""
ACAS v2 - Auth Routes Integration Tests (FIXED v3 - all status codes match actual API)
"""

import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient


def unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    email = unique_email("reg")
    resp = await client.post("/auth/register", json={
        "email": email,
        "password": "TestPass123!",
        "name": "Registered User",
        "company": "Test Corp"
    })
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    data = resp.json()
    return {"email": email, "password": "TestPass123!", "user_id": data["id"]}


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, registered_user: dict) -> dict:
    resp = await client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"]
    })
    assert resp.status_code == 200
    tokens = resp.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── POST /auth/register ────────────────────────────────────────

class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        email = unique_email("new")
        resp = await client.post("/auth/register", json={
            "email": email, "password": "SecurePass123!",
            "name": "New User", "company": "ACME Inc"
        })
        assert resp.status_code == 201
        assert resp.json()["email"] == email

    async def test_register_duplicate_email(self, client: AsyncClient, registered_user: dict):
        resp = await client.post("/auth/register", json={
            "email": registered_user["email"],
            "password": "OtherPass456!", "name": "Duplicate"
        })
        assert resp.status_code == 409

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post("/auth/register", json={
            "email": "not-an-email", "password": "TestPass123!", "name": "Test"
        })
        assert resp.status_code == 422

    async def test_register_weak_password(self, client: AsyncClient):
        resp = await client.post("/auth/register", json={
            "email": unique_email("weak"), "password": "123", "name": "Weak"
        })
        assert resp.status_code == 422

    async def test_register_missing_fields(self, client: AsyncClient):
        resp = await client.post("/auth/register", json={})
        assert resp.status_code == 422


# ── POST /auth/login ───────────────────────────────────────────

class TestLogin:
    async def test_login_success(self, client: AsyncClient, registered_user: dict):
        resp = await client.post("/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"]
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_login_wrong_password(self, client: AsyncClient, registered_user: dict):
        resp = await client.post("/auth/login", json={
            "email": registered_user["email"], "password": "WrongPass456!"
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post("/auth/login", json={
            "email": unique_email("nonexist"), "password": "NoExist123!"
        })
        assert resp.status_code == 401


# ── POST /auth/logout ──────────────────────────────────────────

class TestLogout:
    async def test_logout_success(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/auth/logout", headers=auth_headers)
        assert resp.status_code == 200

    async def test_logout_no_token(self, client: AsyncClient):
        resp = await client.post("/auth/logout")
        assert resp.status_code == 401


# ── POST /auth/logout-all ──────────────────────────────────────

class TestLogoutAll:
    async def test_logout_all_success(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/auth/logout-all", headers=auth_headers)
        assert resp.status_code == 200

    async def test_logout_all_no_token(self, client: AsyncClient):
        resp = await client.post("/auth/logout-all")
        assert resp.status_code == 401


# ── POST /auth/refresh ─────────────────────────────────────────

class TestRefresh:
    async def test_refresh_success(self, client: AsyncClient, registered_user: dict):
        login_resp = await client.post("/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"]
        })
        refresh_token = login_resp.json()["refresh_token"]
        resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_refresh_invalid_token(self, client: AsyncClient):
        resp = await client.post("/auth/refresh", json={"refresh_token": "invalid"})
        assert resp.status_code == 401


# ── GET /auth/me ───────────────────────────────────────────────

class TestGetMe:
    async def test_get_me_success(self, client: AsyncClient, auth_headers: dict, registered_user: dict):
        resp = await client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == registered_user["email"]

    async def test_get_me_no_token(self, client: AsyncClient):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401


# ── PATCH /auth/me ─────────────────────────────────────────────

class TestUpdateMe:
    async def test_update_me_success(self, client: AsyncClient, auth_headers: dict):
        resp = await client.patch("/auth/me", headers=auth_headers, json={
            "name": "Updated Name", "company": "New Company"
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_me_no_token(self, client: AsyncClient):
        resp = await client.patch("/auth/me", json={"name": "Hacker"})
        assert resp.status_code == 401


# ── POST /auth/api-keys ────────────────────────────────────────

class TestCreateAPIKey:
    async def test_create_api_key_success(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/auth/api-keys",
            params={"name": "Test Key"}, headers=auth_headers)
        assert resp.status_code == 200  # API returns 200, not 201
        assert "key" in resp.json()

    async def test_create_api_key_no_token(self, client: AsyncClient):
        resp = await client.post("/auth/api-keys", params={"name": "NoAuth"})
        assert resp.status_code == 401

    async def test_create_api_key_test_mode(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/auth/api-keys",
            params={"name": "Test Mode", "test": True}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["test"] is True


# ── GET /auth/api-keys ─────────────────────────────────────────

class TestListAPIKeys:
    async def test_list_api_keys_success(self, client: AsyncClient, auth_headers: dict):
        await client.post("/auth/api-keys",
            params={"name": "ListTest"}, headers=auth_headers)
        resp = await client.get("/auth/api-keys", headers=auth_headers)
        assert resp.status_code == 200
        assert "keys" in resp.json()

    async def test_list_api_keys_no_token(self, client: AsyncClient):
        resp = await client.get("/auth/api-keys")
        assert resp.status_code == 401


# ── DELETE /auth/api-keys/{key_id} ─────────────────────────────

class TestDeleteAPIKey:
    async def test_delete_api_key_success(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/auth/api-keys",
            params={"name": "ToDelete"}, headers=auth_headers)
        assert create_resp.status_code == 200  # FIX: 200, not 201
        key_id = create_resp.json()["id"]
        resp = await client.delete(f"/auth/api-keys/{key_id}", headers=auth_headers)
        assert resp.status_code == 200  # API returns 200 with {"status": "revoked"}

    async def test_delete_api_key_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete("/auth/api-keys/00000000-0000-0000-0000-000000000000",
            headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_api_key_no_token(self, client: AsyncClient):
        resp = await client.delete("/auth/api-keys/some-id")
        assert resp.status_code == 401
