"""
ACAS v2 - Rate Limiter Coverage Boost (FAST)
Target: Quickly cover missing lines in rate_limit.py
Strategy: 1 test per untested method
"""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import time

from src.core.rate_limit import RateLimiter, RateLimitStrategy, RateLimitResult


class TestSlidingWindow:
    """Test _sliding_window_sync method"""

    async def test_sliding_window_allows(self):
        """Test sliding window when under limit"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.pipeline.return_value.execute.return_value = [0, 5, True, True]  # 5 < 10
        
        result = await rl._run_in_thread(rl._sliding_window_sync, "test_key", 10, 60)
        assert result.allowed is True

    async def test_sliding_window_denies(self):
        """Test sliding window when over limit"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.pipeline.return_value.execute.return_value = [0, 10, True, True]  # 10 >= 10
        rl._redis.zrem.return_value = 1
        rl._redis.zrange.return_value = [("1.0", 1.0)]
        
        result = await rl._run_in_thread(rl._sliding_window_sync, "test_key", 10, 60)
        assert result.allowed is False


class TestFixedWindow:
    """Test _fixed_window_sync method"""

    async def test_fixed_window_allows(self):
        """Test fixed window when under limit"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        # Mock incr to return 5 (under limit of 10)
        rl._redis.incr.return_value = 5
        rl._redis.expire.return_value = True
        
        result = await rl._run_in_thread(rl._fixed_window_sync, "test_key", 10, 60)
        assert result.allowed is True

    async def test_fixed_window_denies(self):
        """Test fixed window when over limit"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = "10"  # 10 >= 10
        rl._redis.ttl.return_value = 30
        
        result = await rl._run_in_thread(rl._fixed_window_sync, "test_key", 10, 60)
        assert result.allowed is False

    async def test_fixed_window_first_request(self):
        """Test fixed window on first request"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = None  # No previous requests
        
        result = await rl._run_in_thread(rl._fixed_window_sync, "test_key", 10, 60)
        assert result.allowed is True
        rl._redis.incr.assert_called_once()


class TestTokenBucket:
    """Test _token_bucket_sync method"""

    async def test_token_bucket_allows(self):
        """Test token bucket when tokens available"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.hget.side_effect = ["5", str(time.time())]  # 5 tokens available
        
        result = await rl._run_in_thread(rl._token_bucket_sync, "test_key", 10, 60)
        assert result.allowed is True

    async def test_token_bucket_denies(self):
        """Test token bucket when no tokens"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.hget.side_effect = ["0", str(time.time())]  # 0 tokens
        
        result = await rl._run_in_thread(rl._token_bucket_sync, "test_key", 10, 60)
        assert result.allowed is False


class TestCheckMethod:
    """Test check() method with different strategies"""

    async def test_check_sliding_window(self):
        """Test check() with sliding window strategy"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.pipeline.return_value.execute.return_value = [0, 5, True, True]
        
        result = await rl.check("test_key", strategy=RateLimitStrategy.SLIDING_WINDOW)
        assert result.allowed is True

    async def test_check_fixed_window(self):
        """Test check() with fixed window strategy"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = "5"
        
        result = await rl.check("test_key", strategy=RateLimitStrategy.FIXED_WINDOW)
        assert result.allowed is True

    async def test_check_token_bucket(self):
        """Test check() with token bucket strategy"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.hget.side_effect = ["5", str(time.time())]
        
        result = await rl.check("test_key", strategy=RateLimitStrategy.TOKEN_BUCKET)
        assert result.allowed is True


class TestLoginBlocked:
    """Test is_login_blocked method"""

    async def test_login_blocked_true(self):
        """Test when login should be blocked"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = "10"  # 10 >= 5
        
        result = await rl.is_login_blocked("127.0.0.1", "test@example.com")
        assert result is True

    async def test_login_blocked_false(self):
        """Test when login should not be blocked"""
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = "3"  # 3 < 5
        
        result = await rl.is_login_blocked("127.0.0.1", "test@example.com")
        assert result is False
