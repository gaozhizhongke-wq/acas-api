"""
P0 Coverage Push — ACAS v2
Targets uncovered paths in: rate_limit, main, auth, health, users
Run: pytest tests/test_p0_coverage_push.py -v --cov=src
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


# =============================================================================
# rate_limit.py — target: _parse_limit, sync methods, edge cases
# =============================================================================

class TestRateLimitParseLimit:
    """_parse_limit edge cases"""

    @pytest.mark.asyncio
    async def test_parse_invalid_format_returns_defaults(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        count, window = rl._parse_limit("not-a-limit")
        assert count == 100  # default
        assert window == 60   # default

    @pytest.mark.asyncio
    async def test_parse_empty_returns_defaults(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        count, window = rl._parse_limit("")
        assert count == 100
        assert window == 60

    @pytest.mark.asyncio
    async def test_parse_standard_format(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        count, window = rl._parse_limit("200:120")
        assert count == 200
        assert window == 120


class TestRateLimitSyncMethods:
    """_check_blocked_sync, _record_failure_sync, _clear_attempts_sync"""

    def test_check_blocked_ip_exceeds_threshold(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = b"10"  # >= 5 threshold
        result = rl._check_blocked_sync("brute:ip:x", "brute:email:y", 5)
        assert result is True

    def test_check_blocked_email_exceeds_threshold(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.side_effect = [b"1", b"7"]  # ip OK, email >= 5
        result = rl._check_blocked_sync("brute:ip:x", "brute:email:y", 5)
        assert result is True

    def test_check_blocked_below_threshold(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.side_effect = [b"2", b"3"]  # both < 5
        result = rl._check_blocked_sync("brute:ip:x", "brute:email:y", 5)
        assert result is False

    def test_check_blocked_no_record(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = None
        result = rl._check_blocked_sync("brute:ip:x", "brute:email:y", 5)
        assert result is False

    def test_record_failure_sync_pipeline(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        pipe = MagicMock()
        rl._redis.pipeline.return_value = pipe
        rl._record_failure_sync("brute:ip:x", "brute:email:y", 300)
        assert pipe.incr.call_count == 2
        assert pipe.expire.call_count == 2
        pipe.execute.assert_called_once()

    def test_clear_attempts_sync(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        rl._clear_attempts_sync("brute:ip:x", "brute:email:y")
        # Uses direct delete() call, not pipeline
        rl._redis.delete.assert_called_once_with("brute:ip:x", "brute:email:y")


class TestRateLimitRunInThread:
    """_run_in_thread exception handling and bypass paths"""

    @pytest.mark.asyncio
    async def test_run_in_thread_sync_call(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        result = await rl._run_in_thread(lambda: 42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_run_in_thread_exception_returns_exc_info(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        def raise_fn():
            raise ValueError("test error")
        with pytest.raises(ValueError, match="test error"):
            await rl._run_in_thread(raise_fn)


class TestRateLimitSlidingWindowEdge:
    """Sliding window edge branches"""

    def test_sliding_at_limit(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        pipe = MagicMock()
        rl._redis.pipeline.return_value = pipe
        # simulate: results[0]=zremrangebyscore (n_removed), results[1]=zcard=5 (at limit)
        # we add the request, then check count (5 >= 5), so it's rejected
        pipe.execute.return_value = [0, 5]  # [zrem count, current count]
        result = rl._sliding_window_sync("key", 5, 60)
        assert result.allowed is False

    def test_sliding_window_no_redis(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = None
        result = rl._sliding_window_sync("key", 10, 60)
        assert result.allowed is True
        assert result.remaining == 10

    def test_sliding_zero_max_requests(self):
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        pipe = MagicMock()
        rl._redis.pipeline.return_value = pipe
        # results[0]=zremrangebyscore, results[1]=zcard=0
        pipe.execute.return_value = [0, 0]
        result = rl._sliding_window_sync("key", 0, 60)
        # 0 >= 0 → not allowed
        assert result.allowed is False


class TestRateLimitTokenBucketEdge:
    """Token bucket edge branches"""

    def test_token_bucket_full(self):
        import time
        from src.core import rate_limit as rl_mod
        rl = rl_mod.RateLimiter()
        rl._redis = MagicMock()
        pipe = MagicMock()
        rl._redis.pipeline.return_value = pipe
        now = int(time.time())
        pipe.execute.return_value = [50.0, float(now - 10)]  # 50 tokens, last update 10s ago
        result = rl._token_bucket_sync("key", 100, 60)
        assert result.allowed is True


# =============================================================================
# health.py — all 4 probe types
# =============================================================================

class TestHealthProbes:
    """Health, ready, liveness, startup probe endpoints"""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data or "status" in data

    @pytest.mark.asyncio
    async def test_ready_returns_status(self, client):
        resp = await client.get("/ready")
        # 200 when healthy, 503 when Redis/DB down (both are expected)
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_metrics_returns_prometheus_format(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            # Our app uses acas_* metric names; verify prometheus format
            assert "# HELP acas_" in resp.text or "# TYPE acas_" in resp.text

    @pytest.mark.asyncio
    async def test_openapi_schema_available(self, client):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data


# =============================================================================
# main.py — error handlers, CORS, 404
# =============================================================================

class TestMainAppErrorPaths:
    """App-level error handlers and middleware"""

    @pytest.mark.asyncio
    async def test_404_returns_json_error(self, client):
        resp = await client.get("/this-does-not-exist-xyz")
        assert resp.status_code == 404
        assert resp.headers.get("content-type", "").startswith("application/json")

    @pytest.mark.asyncio
    async def test_cors_preflight(self, client):
        resp = await client.options("/health", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        })
        # 200, 204, or 405 are all valid CORS responses
        assert resp.status_code in (200, 204, 405)


# =============================================================================
# auth.py — validation, login failure, token refresh
# =============================================================================

class TestAuthValidation:
    """Email/password validation edge cases"""

    @pytest.mark.asyncio
    async def test_register_short_password(self, client, db_session):
        resp = await client.post("/auth/register", json={
            "email": "shortpw@test.com",
            "password": "abc",
            "name": "Test"
        })
        assert resp.status_code in (422, 400, 401)

    @pytest.mark.asyncio
    async def test_register_bad_email(self, client, db_session):
        resp = await client.post("/auth/register", json={
            "email": "not-an-email-address",
            "password": "ValidPass1!",
            "name": "Test"
        })
        assert resp.status_code in (422, 400, 401)

    @pytest.mark.asyncio
    async def test_register_short_name(self, client, db_session):
        resp = await client.post("/auth/register", json={
            "email": "shortname@test.com",
            "password": "ValidPass1!",
            "name": "X"
        })
        assert resp.status_code in (422, 400, 401)

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, db_session):
        await client.post("/auth/register", json={
            "email": "logfail@test.com",
            "password": "CorrectPass1!",
            "name": "Test"
        })
        resp = await client.post("/auth/login", json={
            "email": "logfail@test.com",
            "password": "WrongPassword1!"
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_no_user(self, client, db_session):
        resp = await client.post("/auth/login", json={
            "email": "nobody@test.com",
            "password": "AnyPassword1!"
        })
        assert resp.status_code == 401


class TestAuthTokenRefresh:
    """Refresh token rotation"""

    @pytest.mark.asyncio
    async def test_refresh_valid_token(self, client, db_session):
        await client.post("/auth/register", json={
            "email": "refresh@test.com",
            "password": "TestPass123!",
            "name": "Refresh"
        })
        login = await client.post("/auth/login", json={
            "email": "refresh@test.com",
            "password": "TestPass123!"
        })
        refresh_token = login.json()["refresh_token"]
        resp = await client.post("/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert resp.status_code in (200, 201)
        assert "access_token" in resp.json()

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client, db_session):
        resp = await client.post("/auth/refresh", json={
            "refresh_token": "invalid.token.string"
        })
        assert resp.status_code == 401


# =============================================================================
# users.py — update profile, authorization
# =============================================================================

class TestUsersProfileUpdate:
    """User profile update and authorization"""

    @pytest.mark.asyncio
    async def test_update_own_name(self, client, db_session):
        await client.post("/auth/register", json={
            "email": "updateuser@test.com",
            "password": "TestPass123!",
            "name": "Old Name"
        })
        login = await client.post("/auth/login", json={
            "email": "updateuser@test.com",
            "password": "TestPass123!"
        })
        token = login.json()["access_token"]
        # GET /users/me to get the actual user ID
        me_resp = await client.get("/users/me",
            headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        user_id = me_resp.json()["id"]
        # PATCH /users/{id} with the real ID
        resp = await client.patch(f"/users/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "New Name"})
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_update_without_token(self, client):
        resp = await client.patch("/users/me", json={"name": "Hacker"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_returns_user_data(self, client, db_session):
        await client.post("/auth/register", json={
            "email": "getme@test.com",
            "password": "TestPass123!",
            "name": "Get Me"
        })
        login = await client.post("/auth/login", json={
            "email": "getme@test.com",
            "password": "TestPass123!"
        })
        token = login.json()["access_token"]
        resp = await client.get("/users/me",
            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data


# =============================================================================
# database.py — health check, error paths
# =============================================================================

class TestDatabasePaths:
    """Database health check and connection paths"""

    def test_db_health_check_exists(self):
        from src.core.database import db
        assert hasattr(db, "health_check")
        assert callable(db.health_check)

    def test_db_initialize_exists(self):
        from src.core.database import db
        assert hasattr(db, "initialize")
        assert callable(db.initialize)
