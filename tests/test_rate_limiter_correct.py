"""
ACAS v2 - RateLimiter Correct Tests
Based on actual rate_limit.py API
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import time

from src.core.rate_limit import RateLimiter, RateLimitStrategy, RateLimitResult


class TestRateLimiterInit:
    """Test RateLimiter initialization"""

    def test_init(self):
        rl = RateLimiter()
        assert rl._redis is None
        assert rl._local_cache == {}
        assert rl._loop is None


class TestRateLimiterConnect:
    """Test RateLimiter.connect()"""

    async def test_connect_disabled(self):
        """Test connect when rate limiting is disabled"""
        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = False
            rl = RateLimiter()
            await rl.connect()
            assert rl._redis is None

    async def test_connect_success(self):
        """Test connect when Redis is available"""
        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = True
            mock_config.redis.get_password.return_value = "test"
            mock_config.redis.get_host.return_value = "localhost"
            mock_config.redis.get_port.return_value = 6379
            mock_config.redis.get_db.return_value = 0
            mock_config.redis.socket_timeout = 5
            mock_config.redis.socket_connect_timeout = 5
            mock_config.redis.retry_on_timeout = True
            
            with patch("src.core.rate_limit.redis.Redis") as MockRedis:
                mock_client = MagicMock()
                mock_client.ping.return_value = True
                MockRedis.return_value = mock_client
                
                rl = RateLimiter()
                await rl.connect()
                assert rl._redis is not None


class TestRateLimiterCheck:
    """Test RateLimiter.check()"""

    async def test_check_disabled(self):
        """Test check when rate limiting is disabled"""
        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = False
            
            rl = RateLimiter()
            result = await rl.check("test_key")
            assert result.allowed is True
            assert result.remaining == 999

    async def test_check_no_redis(self):
        """Test check when Redis is not connected"""
        rl = RateLimiter()
        rl._redis = None
        
        result = await rl.check("test_key")
        assert result.allowed is True


class TestRateLimitResult:
    """Test RateLimitResult"""

    def test_create(self):
        result = RateLimitResult(allowed=True, remaining=5, reset_time=int(time.time()) + 60)
        assert result.allowed is True
        assert result.remaining == 5

    def test_create_denied(self):
        result = RateLimitResult(allowed=False, remaining=0, reset_time=int(time.time()) + 60, retry_after=60)
        assert result.allowed is False
        assert result.retry_after == 60


class TestLoginRateLimiting:
    """Test login rate limiting methods"""

    async def test_is_login_blocked_disabled(self):
        """Test is_login_blocked when disabled"""
        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = False
            
            rl = RateLimiter()
            blocked = await rl.is_login_blocked("127.0.0.1", "test@example.com")
            assert blocked is False

    async def test_record_login_failure_disabled(self):
        """Test record_login_failure when disabled"""
        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = False
            
            rl = RateLimiter()
            await rl.record_login_failure("127.0.0.1", "test@example.com")  # Should not raise

    async def test_clear_login_attempts_disabled(self):
        """Test clear_login_attempts when disabled"""
        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = False
            
            rl = RateLimiter()
            await rl.clear_login_attempts("127.0.0.1", "test@example.com")  # Should not raise
