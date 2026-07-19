"""
ACAS v2 - Authentication Tests
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import User


class TestAuthRegistration:
    """Tests for user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient, test_user_data: dict):
        """Test successful user registration."""
        response = await client.post("/auth/register", json=test_user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == test_user_data["email"]
        assert data["name"] == test_user_data["name"]
        assert data["role"] == "user"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, test_user_data: dict, test_user: User):
        """Test registration with duplicate email fails."""
        response = await client.post("/auth/register", json=test_user_data)

        assert response.status_code == 409
        assert "already registered" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client: AsyncClient):
        """Test registration with weak password fails."""
        response = await client.post(
            "/auth/register",
            json={
                "email": "weak@example.com",
                "password": "short",  # Too short
                "name": "Weak User"
            }
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email fails."""
        response = await client.post(
            "/auth/register",
            json={
                "email": "not-an-email",
                "password": "ValidPassword123",
                "name": "Invalid Email User"
            }
        )

        assert response.status_code == 422


class TestAuthLogin:
    """Tests for login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user_data: dict, test_user: User):
        """Test successful login."""
        response = await client.post(
            "/auth/login",
            json={
                "email": test_user_data["email"],
                "password": test_user_data["password"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user_data: dict, test_user: User):
        """Test login with wrong password fails."""
        response = await client.post(
            "/auth/login",
            json={
                "email": test_user_data["email"],
                "password": "WrongPassword123"
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with nonexistent user fails."""
        response = await client.post(
            "/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "SomePassword123"
            }
        )

        assert response.status_code == 401


class TestAuthMe:
    """Tests for /me endpoint."""

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, client: AsyncClient, auth_headers: dict, test_user: User):
        """Test getting current user info with valid token."""
        response = await client.get("/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["name"] == test_user.name

    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, client: AsyncClient):
        """Test getting current user info without token fails."""
        response = await client.get("/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client: AsyncClient):
        """Test getting current user info with invalid token fails."""
        response = await client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401


class TestAuthLogout:
    """Tests for logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful logout."""
        response = await client.post("/auth/logout", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "logged_out"

    @pytest.mark.asyncio
    async def test_logout_twice_fails(self, client: AsyncClient, auth_headers: dict):
        """Test that using a revoked token fails."""
        # First logout
        await client.post("/auth/logout", headers=auth_headers)

        # Try to use the same token again
        response = await client.get("/auth/me", headers=auth_headers)

        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()


class TestTokenRefresh:
    """Tests for token refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient, test_user_data: dict, test_user: User):
        """Test successful token refresh."""
        # First login
        login_response = await client.post(
            "/auth/login",
            json={
                "email": test_user_data["email"],
                "password": test_user_data["password"]
            }
        )

        refresh_token = login_response.json()["refresh_token"]

        # Refresh
        response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # New tokens should be different
        assert data["refresh_token"] != refresh_token


class TestAPIKeys:
    """Tests for API key management."""

    @pytest.mark.asyncio
    async def test_create_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test creating an API key."""
        response = await client.post(
            "/auth/api-keys?name=Test Key&test=true",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "key" in data
        assert data["name"] == "Test Key"
        assert data["test"] is True

    @pytest.mark.asyncio
    async def test_list_api_keys(self, client: AsyncClient, auth_headers: dict):
        """Test listing API keys."""
        # Create a key first
        await client.post("/auth/api-keys?name=List Test Key", headers=auth_headers)

        # List keys
        response = await client.get("/auth/api-keys", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert len(data["keys"]) >= 1

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test revoking an API key."""
        # Create a key
        create_response = await client.post(
            "/auth/api-keys?name=Revoke Test Key",
            headers=auth_headers
        )
        key_id = create_response.json()["id"]

        # Revoke it
        response = await client.delete(f"/auth/api-keys/{key_id}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "revoked"
