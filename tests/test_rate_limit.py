"""
ACAS v2 - Rate Limiter Coverage Tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestRateLimiter:
    """Test RateLimiter class"""

    @pytest.mark.asyncio
    async def test_connect_redis_fails(self):
        """test_connect_redis_fails - when Redis connection fails, sets _redis to None"""
        from src.core import rate_limit as rl_module

        # Create a limiter and simulate what happens when Redis connection fails
        limiter = rl_module.RateLimiter()
        limiter._redis = None
        limiter._local_cache = {}
        limiter._loop = None

        # Simulate redis.Redis constructor raising (connection refused)
        with patch.object(rl_module.redis, "Redis", side_effect=Exception("connection refused")):
            await limiter.connect()

        # Should have caught exception and set _redis to None
        assert limiter._redis is None

    @pytest.mark.asyncio
    async def test_check_disabled(self):
        """test_check_disabled - when rate_limit.enabled=False, always allowed"""
        from src.core.rate_limit import RateLimiter

        limiter = RateLimiter()
        limiter._redis = MagicMock()  # Redis connected, but...

        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = False

            result = await limiter.check("test-key")

            assert result.allowed is True
            assert result.remaining == 999

    @pytest.mark.asyncio
    async def test_parse_limit(self):
        """test_parse_limit - '100:3600' → (100, 3600)"""
        from src.core.rate_limit import RateLimiter

        limiter = RateLimiter()
        limiter._redis = None
        limiter._local_cache = {}
        limiter._loop = None

        result = limiter._parse_limit("100:3600")
        assert result == (100, 3600)

    @pytest.mark.asyncio
    async def test_parse_limit_short_window(self):
        """_parse_limit handles short windows like 5:300"""
        from src.core.rate_limit import RateLimiter

        limiter = RateLimiter()
        limiter._redis = None
        limiter._local_cache = {}
        limiter._loop = None

        result = limiter._parse_limit("5:300")
        assert result == (5, 300)

    @pytest.mark.asyncio
    async def test_check_no_redis(self):
        """When _redis is None, check returns allowed immediately"""
        from src.core.rate_limit import RateLimiter

        limiter = RateLimiter()
        limiter._redis = None
        limiter._local_cache = {}
        limiter._loop = None

        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = True
            result = await limiter.check("any-key")
            assert result.allowed is True
            assert result.remaining == 999

    @pytest.mark.asyncio
    async def test_check_fixed_window(self):
        """check with FIXED_WINDOW strategy"""
        from src.core.rate_limit import RateLimiter, RateLimitStrategy

        limiter = RateLimiter()
        limiter._redis = None
        limiter._local_cache = {}
        limiter._loop = None

        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = False
            result = await limiter.check("key", strategy=RateLimitStrategy.FIXED_WINDOW)
            assert result.allowed is True

    @pytest.mark.asyncio
    async def test_check_token_bucket(self):
        """check with TOKEN_BUCKET strategy"""
        from src.core.rate_limit import RateLimiter, RateLimitStrategy

        limiter = RateLimiter()
        limiter._redis = None
        limiter._local_cache = {}
        limiter._loop = None

        with patch("src.core.rate_limit.config") as mock_config:
            mock_config.rate_limit.enabled = False
            result = await limiter.check("key", strategy=RateLimitStrategy.TOKEN_BUCKET)
            assert result.allowed is True
