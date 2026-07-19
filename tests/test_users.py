"""
ACAS v2 - User Management Tests
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import User


class TestUserList:
    """Tests for listing users."""

    @pytest.mark.asyncio
    async def test_list_users_admin(self, client: AsyncClient, admin_user: User, db_session: AsyncSession):
        """Test admin can list users."""
        # Login as admin
        login_response = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        # Create some test users
        from src.core.security import password_manager
        for i in range(3):
            user = User(
                email=f"user{i}@example.com",
                name=f"User {i}",
                hashed_password=password_manager.hash("Password123!"),
                role="user"
            )
            db_session.add(user)
        await db_session.commit()

        # List users
        response = await client.get("/users/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] >= 4  # 3 created + 1 admin

    @pytest.mark.asyncio
    async def test_list_users_non_admin(self, client: AsyncClient, auth_headers: dict):
        """Test non-admin cannot list users."""
        response = await client.get("/users/", headers=auth_headers)

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_with_filter(self, client: AsyncClient, admin_user: User, db_session: AsyncSession):
        """Test listing users with role filter."""
        # Login as admin
        login_response = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        # Filter by role
        response = await client.get("/users/?role=admin", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert all(u["role"] == "admin" for u in data["users"])


class TestUserGet:
    """Tests for getting a single user."""

    @pytest.mark.asyncio
    async def test_get_self(self, client: AsyncClient, auth_headers: dict, test_user: User):
        """Test user can get their own profile."""
        response = await client.get(f"/users/{test_user.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_get_other_user_as_non_admin(self, client: AsyncClient, auth_headers: dict, admin_user: User):
        """Test non-admin cannot get other user's profile."""
        response = await client.get(f"/users/{admin_user.id}", headers=auth_headers)

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_any_user_as_admin(self, client: AsyncClient, admin_user: User, test_user: User):
        """Test admin can get any user's profile."""
        # Login as admin
        login_response = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = await client.get(f"/users/{test_user.id}", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, client: AsyncClient, admin_user: User):
        """Test getting nonexistent user returns 404."""
        # Login as admin
        login_response = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = await client.get("/users/00000000-0000-0000-0000-000000000000", headers=admin_headers)

        assert response.status_code == 404


class TestUserUpdate:
    """Tests for updating users."""

    @pytest.mark.asyncio
    async def test_update_self_name(self, client: AsyncClient, auth_headers: dict, test_user: User):
        """Test user can update their own name."""
        response = await client.patch(
            f"/users/{test_user.id}",
            json={"name": "New Name"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_admin_can_update_role(self, client: AsyncClient, admin_user: User, test_user: User):
        """Test admin can update user role."""
        # Login as admin
        login_response = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = await client.patch(
            f"/users/{test_user.id}",
            json={"role": "analyst"},
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "analyst"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_update_role(self, client: AsyncClient, auth_headers: dict, test_user: User):
        """Test non-admin cannot update role."""
        response = await client.patch(
            f"/users/{test_user.id}",
            json={"role": "admin"},
            headers=auth_headers
        )

        # Role change should be ignored, but name can still be changed
        assert response.status_code == 200
        assert response.json()["role"] == "user"  # Role unchanged

    @pytest.mark.asyncio
    async def test_admin_cannot_deactivate_self(self, client: AsyncClient, admin_user: User):
        """Test admin cannot deactivate their own account."""
        # Login as admin
        login_response = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = await client.patch(
            f"/users/{admin_user.id}",
            json={"is_active": False},
            headers=admin_headers
        )

        assert response.status_code == 400


class TestUserDeactivate:
    """Tests for deactivating users."""

    @pytest.mark.asyncio
    async def test_deactivate_self(self, client: AsyncClient, auth_headers: dict, test_user: User):
        """Test user can deactivate their own account."""
        response = await client.delete(f"/users/{test_user.id}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "deactivated"

    @pytest.mark.asyncio
    async def test_admin_cannot_deactivate_self(self, client: AsyncClient, admin_user: User):
        """Test admin cannot deactivate their own account."""
        # Login as admin
        login_response = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = await client.delete(f"/users/{admin_user.id}", headers=admin_headers)

        assert response.status_code == 400
        assert "cannot deactivate" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_can_deactivate_other(self, client: AsyncClient, admin_user: User, test_user: User):
        """Test admin can deactivate other users."""
        # Login as admin
        login_response = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = await client.delete(f"/users/{test_user.id}", headers=admin_headers)

        assert response.status_code == 200
