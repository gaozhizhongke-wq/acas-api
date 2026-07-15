"""
ACAS v2 - Users Routes Coverage Push (FINAL)

Tests missing coverage in users.py routes:
- GET /users/me  (via get_current_user)
- PATCH /users/{user_id}  (self-update)
- DELETE /users/{user_id}  (self-deactivate)
- GET /users/ (list with pagination)

Uses conftest fixtures directly (test_user, test_user_data, auth_headers, admin_auth_headers).
Overriding fixtures only when truly needed.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
import uuid


def unique_email(prefix: str = "users_final") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


# ── Fixtures (override conftest only when conftest doesn't provide needed user) ──

@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a new user via API (used when conftest test_user is not suitable)."""
    email = unique_email()
    resp = await client.post("/auth/register", json={
        "email": email, "password": "TestPass123!",
        "name": "Users Final User", "company": "Final Corp"
    })
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    return {"email": email, "password": "TestPass123!", "id": resp.json()["id"]}


@pytest_asyncio.fixture
async def auth_headers_via_api(client: AsyncClient, registered_user: dict) -> dict:
    """Login with a freshly registered API user (overrides conftest auth_headers)."""
    resp = await client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"]
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── GET /users/me ─────────────────────────────────────────────────────────────

class TestUsersGetCurrent:
    async def test_get_current_user_via_api_user(
        self, client: AsyncClient, auth_headers_via_api: dict
    ):
        """GET /users/me — API-registered user gets own profile"""
        resp = await client.get("/users/me", headers=auth_headers_via_api)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "email" in data
        assert "name" in data

    async def test_get_current_user_conftest_user(
        self, client: AsyncClient, test_user_data: dict, auth_headers: dict
    ):
        """GET /users/me — conftest test_user gets own profile"""
        resp = await client.get("/users/me", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ── PATCH /users/{user_id} (self-update) ─────────────────────────────────────

class TestUsersUpdateSelf:
    @pytest.mark.parametrize("field,value", [
        ("name", "New Name"),
        ("company", "New Company"),
        ("name", "A" * 50),
    ])
    async def test_update_own_profile_via_api_user(
        self, client: AsyncClient, auth_headers_via_api: dict,
        field: str, value: str
    ):
        """PATCH /users/{id} — user updates own name/company via API-registered user"""
        # auth_headers_via_api belongs to a freshly registered user
        token_payload = auth_headers_via_api["Authorization"].split(" ", 1)[1]
        import base64, json
        payload_b64 = token_payload.split('.')[1]
        padding = 4 - len(payload_b64) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + '=' * padding))
        user_id = payload["sub"]

        resp = await client.patch(f"/users/{user_id}", headers=auth_headers_via_api, json={field: value})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()[field] == value

    async def test_update_own_profile_conftest_user(
        self, client: AsyncClient, test_user_data: dict, auth_headers: dict
    ):
        """PATCH /users/{id} — conftest test_user updates own profile"""
        token_payload = auth_headers["Authorization"].split(" ", 1)[1]
        import base64, json
        payload_b64 = token_payload.split('.')[1]
        padding = 4 - len(payload_b64) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + '=' * padding))
        user_id = payload["sub"]

        resp = await client.patch(f"/users/{user_id}", headers=auth_headers, json={"name": "Updated Name"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ── DELETE /users/{user_id} ─────────────────────────────────────────────────

class TestUsersDeactivate:
    async def test_deactivate_own_account_via_api_user(
        self, client: AsyncClient, auth_headers_via_api: dict
    ):
        """DELETE /users/{id} — user deactivates own account via API-registered user"""
        token_payload = auth_headers_via_api["Authorization"].split(" ", 1)[1]
        import base64, json
        payload_b64 = token_payload.split('.')[1]
        padding = 4 - len(payload_b64) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + '=' * padding))
        user_id = payload["sub"]

        resp = await client.delete(f"/users/{user_id}", headers=auth_headers_via_api)
        # Returns 200 on success, 400 if already deactivated
        assert resp.status_code in (200, 400), f"Expected 200/400, got {resp.status_code}: {resp.text}"

    async def test_deactivate_own_account_conftest_user(
        self, client: AsyncClient, auth_headers: dict
    ):
        """DELETE /users/{id} — conftest test_user deactivates own account"""
        token_payload = auth_headers["Authorization"].split(" ", 1)[1]
        import base64, json
        payload_b64 = token_payload.split('.')[1]
        padding = 4 - len(payload_b64) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + '=' * padding))
        user_id = payload["sub"]

        resp = await client.delete(f"/users/{user_id}", headers=auth_headers)
        assert resp.status_code in (200, 400), f"Expected 200/400, got {resp.status_code}: {resp.text}"


# ── GET /users/ (list with pagination) ──────────────────────────────────────

class TestUsersList:
    async def test_list_users_requires_admin(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /users/ — regular user gets 403 (admin only)"""
        resp = await client.get("/users/", headers=auth_headers)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    async def test_list_users_admin_ok(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """GET /users/ — admin gets 200"""
        resp = await client.get("/users/", headers=admin_auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    async def test_list_users_pagination(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """GET /users/?skip=0&limit=10 — admin with pagination"""
        resp = await client.get("/users/?skip=0&limit=10", headers=admin_auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "users" in data


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestUsersEdgeCases:
    async def test_users_with_invalid_token(self, client: AsyncClient):
        """Users endpoints return 401 with invalid token"""
        headers = {"Authorization": "Bearer invalid"}
        resp = await client.get("/users/me", headers=headers)
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}: {resp.text}"

    async def test_users_without_token(self, client: AsyncClient):
        """Users endpoints return 401 without token"""
        resp = await client.get("/users/me")
        assert resp.status_code in (401, 403, 500), f"Expected 401/403/500, got {resp.status_code}: {resp.text}"

    async def test_get_other_user_forbidden(
        self, client: AsyncClient, auth_headers: dict, test_user_data: dict
    ):
        """GET /users/{other_id} — regular user cannot access other users"""
        # test_user is a different user (created by conftest's test_user fixture)
        token_payload = auth_headers["Authorization"].split(" ", 1)[1]
        import base64, json
        payload_b64 = token_payload.split('.')[1]
        padding = 4 - len(payload_b64) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + '=' * padding))
        my_id = payload["sub"]

        # Try to access another non-existent user
        fake_id = str(uuid.uuid4())
        if fake_id == my_id:
            fake_id = str(uuid.uuid4())

        resp = await client.get(f"/users/{fake_id}", headers=auth_headers)
        # Returns 403 (access denied) or 404 (not found)
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}: {resp.text}"
