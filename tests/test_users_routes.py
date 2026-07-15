"""
ACAS v2 - Users Routes Integration Tests

Covers ALL users.py routes including admin paths.
Relies on conftest fixtures for DB setup and test client.
"""

import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient
from sqlalchemy import text


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


# ── Fixtures (override conftest for integration testing) ────────────────────────

@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a new regular user via API."""
    email = unique_email("reg")
    resp = await client.post("/auth/register", json={
        "email": email, "password": "TestPass123!",
        "name": "Regular User", "company": "User Corp"
    })
    assert resp.status_code == 201
    return {"email": email, "password": "TestPass123!", "id": resp.json()["id"]}


@pytest_asyncio.fixture
async def admin_user(client: AsyncClient, db_session) -> dict:
    """
    Register a new user and promote to admin via direct DB access.
    Uses db_session from conftest so it hits the same test DB.
    """
    email = unique_email("admin")
    resp = await client.post("/auth/register", json={
        "email": email, "password": "AdminPass123!",
        "name": "Admin User", "company": "Admin Corp"
    })
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    # Update role via the test DB session (same DB as conftest fixtures)
    await db_session.execute(
        text("UPDATE users SET role = 'admin' WHERE id = :uid"),
        {"uid": user_id}
    )
    await db_session.commit()

    return {"email": email, "password": "AdminPass123!", "id": user_id}


@pytest_asyncio.fixture
async def user_headers(client: AsyncClient, registered_user: dict) -> dict:
    resp = await client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"]
    })
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient, admin_user: dict) -> dict:
    resp = await client.post("/auth/login", json={
        "email": admin_user["email"],
        "password": admin_user["password"]
    })
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── GET /users ─────────────────────────────────────────────────────────────────

class TestListUsers:
    async def test_list_users_as_admin(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/users/", headers=admin_headers)
        assert resp.status_code == 200

    async def test_list_users_not_admin(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/users/", headers=user_headers)
        assert resp.status_code == 403

    async def test_list_users_no_token(self, client: AsyncClient):
        resp = await client.get("/users/")
        assert resp.status_code == 401


# ── GET /users/{user_id} ──────────────────────────────────────────────────────

class TestGetUser:
    async def test_get_self(self, client: AsyncClient, user_headers: dict, registered_user: dict):
        resp = await client.get(f"/users/{registered_user['id']}", headers=user_headers)
        assert resp.status_code == 200

    async def test_get_other_as_admin(self, client: AsyncClient, admin_headers: dict, registered_user: dict):
        resp = await client.get(f"/users/{registered_user['id']}", headers=admin_headers)
        assert resp.status_code == 200

    async def test_get_other_as_non_admin(self, client: AsyncClient, user_headers: dict, admin_user: dict):
        resp = await client.get(f"/users/{admin_user['id']}", headers=user_headers)
        assert resp.status_code == 403


# ── PATCH /users/{user_id} ────────────────────────────────────────────────────

class TestUpdateUser:
    async def test_update_self(self, client: AsyncClient, user_headers: dict, registered_user: dict):
        resp = await client.patch(
            f"/users/{registered_user['id']}",
            headers=user_headers, json={"name": "Updated"}
        )
        assert resp.status_code == 200

    async def test_update_other_as_admin(self, client: AsyncClient, admin_headers: dict, registered_user: dict):
        resp = await client.patch(
            f"/users/{registered_user['id']}",
            headers=admin_headers, json={"name": "ByAdmin"}
        )
        assert resp.status_code == 200

    async def test_admin_change_role(self, client: AsyncClient, admin_headers: dict, registered_user: dict):
        resp = await client.patch(
            f"/users/{registered_user['id']}",
            headers=admin_headers, json={"role": "admin"}
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    async def test_update_other_as_non_admin(self, client: AsyncClient, user_headers: dict, admin_user: dict):
        resp = await client.patch(
            f"/users/{admin_user['id']}",
            headers=user_headers, json={"name": "Hacker"}
        )
        assert resp.status_code == 403


# ── DELETE /users/{user_id} ──────────────────────────────────────────────────

class TestDeactivateUser:
    async def test_deactivate_self(self, client: AsyncClient, user_headers: dict, registered_user: dict):
        resp = await client.delete(f"/users/{registered_user['id']}", headers=user_headers)
        assert resp.status_code == 200

    async def test_deactivate_other_as_admin(self, client: AsyncClient, admin_headers: dict, registered_user: dict):
        resp = await client.delete(f"/users/{registered_user['id']}", headers=admin_headers)
        assert resp.status_code == 200

    async def test_deactivate_self_as_admin_fail(self, client: AsyncClient, admin_headers: dict, admin_user: dict):
        """Admin cannot deactivate self"""
        resp = await client.delete(f"/users/{admin_user['id']}", headers=admin_headers)
        assert resp.status_code == 400
