"""
ACAS v2 - Security Module Unit Tests
Covers PasswordManager and TokenManager edge cases
"""

import pytest
from src.core.security import password_manager, token_manager


class TestPasswordManager:
    """PasswordManager edge cases"""

    def test_hash_min_password(self):
        """Hashing 8-char password should work"""
        hashed = password_manager.hash("Min8Char!")
        assert isinstance(hashed, str)
        assert len(hashed) > 20

    def test_verify_correct(self):
        """Verification succeeds for correct password"""
        hashed = password_manager.hash("TestPass123!")
        assert password_manager.verify("TestPass123!", hashed)

    def test_verify_wrong(self):
        """Verification fails for wrong password"""
        hashed = password_manager.hash("RealPass123!")
        assert not password_manager.verify("WrongPass456!", hashed)

    def test_needs_rehash_fresh(self):
        """Fresh hash does not need rehash"""
        hashed = password_manager.hash("TestPass123!")
        assert not password_manager.needs_rehash(hashed)

    def test_constant_time_dummy(self):
        """Hash dummy password for timing (no raise)"""
        password_manager.hash("dummy_password_for_timing")


class TestTokenManager:
    """TokenManager unit tests"""

    def test_create_token_pair(self):
        """Token pair created correctly"""
        access, refresh = token_manager.create_token_pair(
            user_id="test-123",
            claims={"role": "admin", "email": "admin@example.com"}
        )
        assert access is not None
        assert refresh is not None
        assert access != refresh

    def test_token_structure(self):
        """Token is a non-empty string with dots (JWT)"""
        access, _ = token_manager.create_token_pair(
            user_id="test-123",
            claims={"role": "user", "email": "test@example.com"}
        )
        assert len(access) > 20
        assert access.count(".") == 2  # JWT format: header.payload.signature

    def test_token_with_claims(self):
        """Custom claims included in token"""
        access, _ = token_manager.create_token_pair(
            user_id="test-123",
            claims={"role": "superadmin", "custom": "value"}
        )
        assert access is not None

    @pytest.mark.asyncio
    async def test_decode_token_valid(self):
        """Decode returns payload for valid token"""
        await token_manager.initialize(redis_client=None)
        access, _ = token_manager.create_token_pair(
            user_id="test-123",
            claims={"role": "user", "email": "test@example.com"}
        )
        payload = await token_manager.decode_token(access)
        assert payload is not None
        assert payload.get("sub") == "test-123"

    @pytest.mark.asyncio
    async def test_decode_token_invalid(self):
        """Decode raises for invalid token"""
        await token_manager.initialize(redis_client=None)
        from src.core.security import AuthenticationError
        with pytest.raises(AuthenticationError):
            await token_manager.decode_token("invalid.token.here")

    @pytest.mark.asyncio
    async def test_rotate_refresh_token(self):
        """Rotate refresh token returns 3-tuple (access,refresh,session_id)"""
        await token_manager.initialize(redis_client=None)
        access, refresh = token_manager.create_token_pair(
            user_id="test-123",
            claims={"role": "user", "email": "test@example.com"}
        )
        result = await token_manager.rotate_refresh_token(refresh)
        assert result is not None
        assert len(result) == 3  # (new_access, new_refresh, session_id)

    @pytest.mark.asyncio
    async def test_rotate_refresh_invalid(self):
        """Rotate with invalid token raises"""
        from src.core.security import AuthenticationError
        with pytest.raises(AuthenticationError):
            await token_manager.rotate_refresh_token("invalid_refresh")

    @pytest.mark.asyncio
    async def test_revoke_token(self):
        """Revoke should not raise when no redis"""
        await token_manager.initialize(redis_client=None)
        access, _ = token_manager.create_token_pair(
            user_id="test-123",
            claims={"role": "user", "email": "test@example.com"}
        )
        await token_manager.revoke_token(access)

    @pytest.mark.asyncio
    async def test_revoke_session(self):
        """Revoke session should not raise"""
        await token_manager.initialize(redis_client=None)
        await token_manager.revoke_session("session_123")

    @pytest.mark.asyncio
    async def test_initialize_twice(self):
        """Re-initialize is idempotent"""
        await token_manager.initialize(redis_client=None)
        await token_manager.initialize(redis_client=None)
        access, _ = token_manager.create_token_pair(
            user_id="test-123",
            claims={"role": "user", "email": "test@example.com"}
        )
        payload = await token_manager.decode_token(access)
        assert payload is not None
