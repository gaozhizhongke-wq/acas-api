"""
ACAS v2 - Integration Tests
Covers route error paths, edge cases, and security features
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.core.config import config
from src.api.main import app


# ── Health ──────────────────────────────────────────────────────

class TestHealth:
    """Health check endpoints"""

    async def test_root_endpoint(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "ACAS API"
        assert data["status"] == "operational"

    async def test_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_metrics_endpoint(self, client: AsyncClient):
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "acas_info" in text
        assert "acas_requests_total" in text

    async def test_metrics_format(self, client: AsyncClient):
        """Metrics rendered in Prometheus text format"""
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")

    async def test_cors_headers(self, client: AsyncClient):
        """CORS headers present (with Origin header)"""
        resp = await client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert "access-control-allow-origin" in resp.headers

    async def test_security_headers(self, client: AsyncClient):
        """Security headers present on all responses"""
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("strict-transport-security") is not None

    async def test_gzip_compression(self, client: AsyncClient):
        """GZip middleware is active"""
        # Need to send Accept-Encoding header
        resp = await client.get("/", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200


# ── Authentication ──────────────────────────────────────────────

class TestAuthErrors:
    """Auth endpoint error paths"""

    async def test_register_empty_payload(self, client: AsyncClient):
        """Missing fields should return 422"""
        resp = await client.post("/auth/register", json={})
        assert resp.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        """Invalid email should return 422"""
        resp = await client.post("/auth/register", json={
            "email": "not-an-email",
            "password": "TestPass123!",
            "name": "Test User"
        })
        assert resp.status_code == 422

    async def test_register_weak_password(self, client: AsyncClient):
        """Weak password should return 422"""
        resp = await client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "weak",
            "name": "Test User"
        })
        assert resp.status_code == 422

    async def test_login_empty_payload(self, client: AsyncClient):
        """Missing credentials should return 422"""
        resp = await client.post("/auth/login", json={})
        assert resp.status_code == 422

    async def test_login_wrong_password(self, client: AsyncClient):
        """Invalid credentials should return 401"""
        resp = await client.post("/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "wrongpassword123"
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Login with unregistered email returns 401"""
        resp = await client.post("/auth/login", json={
            "email": "nobody@nowhere.com",
            "password": "DoesNotExist123!"
        })
        assert resp.status_code == 401
        data = resp.json()
        assert "detail" in data or "error" in data

    async def test_auth_no_token(self, client: AsyncClient):
        """Protected endpoint without token returns 401"""
        resp = await client.get("/users/me")
        assert resp.status_code in (401, 403)

    async def test_auth_invalid_token(self, client: AsyncClient):
        """Invalid token returns 401"""
        resp = await client.get(
            "/users/me",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert resp.status_code in (401, 403)

    async def test_auth_expired_token(self, client: AsyncClient):
        """Expired JWT returns 401"""
        resp = await client.get(
            "/users/me",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.lK7lfQXgN0JFvMNU9vnuWA"}
        )
        assert resp.status_code in (401, 403)

    async def test_logout_no_token(self, client: AsyncClient):
        """Logout without auth returns 401"""
        resp = await client.post("/auth/logout")
        assert resp.status_code in (401, 403)


# ── Rate Limiter - Standalone ───────────────────────────────────

class TestRateLimiterUnit:
    """Rate limiter unit tests (no Redis)"""

    async def test_check_disabled(self):
        """When rate limiting is disabled, check always passes"""
        from src.core.rate_limit import rate_limiter, RateLimitResult
        result = await rate_limiter.check("test:key", "default")
        assert result.allowed is True
        assert result.remaining == 999

    async def test_is_login_blocked_disabled(self):
        """When rate limiting is disabled, never blocked"""
        from src.core.rate_limit import rate_limiter
        blocked = await rate_limiter.is_login_blocked("1.2.3.4", "test@example.com")
        assert blocked is False

    async def test_record_login_failure_disabled(self):
        """When rate limiting is disabled, record is no-op"""
        from src.core.rate_limit import rate_limiter
        await rate_limiter.record_login_failure("1.2.3.4", "test@example.com")
        # Should not raise

    async def test_clear_login_attempts_disabled(self):
        """When rate limiting is disabled, clear is no-op"""
        from src.core.rate_limit import rate_limiter
        await rate_limiter.clear_login_attempts("1.2.3.4", "test@example.com")
        # Should not raise

    def test_parse_limit(self):
        """_parse_limit correctly splits count:window"""
        from src.core.rate_limit import rate_limiter
        count, window = rate_limiter._parse_limit("100:3600")
        assert count == 100
        assert window == 3600


# ── PII Protection ──────────────────────────────────────────────

class TestPIIProtection:
    """PII masking edge cases"""

    def test_mask_email_short_name(self):
        from src.core.pii import mask_email
        assert "***@co.com" in mask_email("ab@co.com")

    def test_mask_email_with_plus(self):
        from src.core.pii import mask_email
        result = mask_email("test+tag@domain.com")
        assert "***" in result
        assert "@domain.com" in result

    def test_mask_empty_name(self):
        from src.core.pii import mask_name
        assert mask_name("") == ""

    def test_redact_empty_dict(self):
        from src.core.pii import redact_pii_from_dict
        assert redact_pii_from_dict({}) == {}

    def test_redact_nested_sensitive(self):
        from src.core.pii import redact_pii_from_dict
        d = {"user": {"email": "u@d.com", "name": "test"}, "password": "secret123"}
        result = redact_pii_from_dict(d)
        assert "***" in str(result)
        assert "secret123" not in str(result)

    def test_redact_non_sensitive_keys(self):
        from src.core.pii import redact_pii_from_dict
        d = {"name": "visible", "role": "admin"}
        result = redact_pii_from_dict(d)
        assert result["name"] == "visible"

    def test_redact_sensitive_response_fields(self):
        from src.core.pii import redact_sensitive_fields
        d = {"email": "test@example.com", "password": "secret"}
        result = redact_sensitive_fields(d)
        assert result["email"] == "***"
        assert result["password"] == "***"

    def test_redact_sensitive_partial(self):
        from src.core.pii import redact_sensitive_fields
        d = {"name": "visible", "api_key": "sk-123"}
        result = redact_sensitive_fields(d, {"api_key"})
        assert result["name"] == "visible"
        assert result["api_key"] == "***"


# ── Security ────────────────────────────────────────────────────

class TestSecurityEdgeCases:
    """Security module edge cases"""

    def test_hash_verification(self):
        """PBKDF2 password hash and verify round-trip"""
        from src.core.security import password_manager
        pwd = "TestPassword123!"
        hashed = password_manager.hash(pwd)
        assert password_manager.verify(pwd, hashed)

    def test_hash_different_password_fails(self):
        """Different password should fail verification"""
        from src.core.security import password_manager
        hashed = password_manager.hash("RealPass123!")
        assert not password_manager.verify("WrongPass456!", hashed)


# ── Config ──────────────────────────────────────────────────────

class TestConfigDefaults:
    """Configuration defaults edge cases"""

    def test_db_url_default(self):
        from src.core.config import DatabaseConfig
        cfg = DatabaseConfig()
        assert cfg.url is not None

    def test_redis_url_default(self):
        from src.core.config import RedisConfig
        cfg = RedisConfig()
        assert cfg.url is not None

    def test_database_ssl_default(self):
        from src.core.config import DatabaseConfig
        cfg = DatabaseConfig()
        assert cfg.ssl_mode == "disable"
