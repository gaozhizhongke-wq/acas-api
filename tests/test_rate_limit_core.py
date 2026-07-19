"""
Deeper coverage for src.core.rate_limit.RateLimiter sync strategies and
brute-force protection, exercised with an in-memory fake Redis.
"""
import time
from unittest.mock import MagicMock

import pytest

from src.core.rate_limit import (
    RateLimiter,
    RateLimitResult,
    RateLimitStrategy,
)


class FakePipe:
    def __init__(self, redis):
        self.redis = redis
        self.calls = []

    def _rec(self, name, *a):
        self.calls.append((name, a))
        return self

    def zremrangebyscore(self, *a):
        return self._rec("zremrangebyscore", *a)

    def zcard(self, *a):
        return self._rec("zcard", *a)

    def zadd(self, *a):
        return self._rec("zadd", *a)

    def expire(self, *a):
        return self._rec("expire", *a)

    def incr(self, *a):
        return self._rec("incr", *a)

    def get(self, key):
        return self._rec("get", key)

    def setex(self, *a):
        return self._rec("setex", *a)

    def execute(self):
        results = []
        for name, a in self.calls:
            if name == "zcard":
                results.append(self.redis.zcard_val)
            elif name == "incr":
                results.append(self.redis.incr_val)
            elif name == "get":
                results.append(self.redis.get(a[0]))
            else:
                results.append(None)
        self.calls = []
        return results


class FakeRedis:
    def __init__(self):
        self.zcard_val = 0
        self.incr_val = 1
        self.tokens = None
        self.last_update = None
        self.store = {}
        self.deleted = []

    def pipeline(self):
        return FakePipe(self)

    def zrem(self, *a):
        return 1

    def zrange(self, *a, **k):
        return []  # no oldest -> reset based on now+window

    def get(self, key):
        k = str(key)
        if "tokens" in k:
            return self.tokens
        if "last_update" in k:
            return self.last_update
        return self.store.get(k)

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def setex(self, *a):
        return True

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
        self.deleted.extend(keys)
        return len(keys)


@pytest.fixture
def rl():
    limiter = RateLimiter()
    fake = FakeRedis()
    old = limiter._redis
    limiter._redis = fake
    yield limiter, fake
    limiter._redis = old


def test_parse_limit_invalid_returns_defaults(rl):
    limiter, _ = rl
    assert limiter._parse_limit("bad") == (100, 60)
    assert limiter._parse_limit("a:b") == (100, 60)
    assert limiter._parse_limit("") == (100, 60)
    assert limiter._parse_limit("5:30") == (5, 30)


@pytest.mark.asyncio
async def test_check_disabled_returns_allowed(rl, monkeypatch):
    from src.core import config
    limiter, _ = rl
    monkeypatch.setattr(config.rate_limit, "enabled", False)
    res = await limiter.check("k", "default")
    assert res.allowed is True
    assert res.remaining == 999


@pytest.mark.asyncio
async def test_check_sliding_window_allowed(rl):
    limiter, fake = rl
    fake.zcard_val = 0
    res = await limiter.check("sw:k", "default", RateLimitStrategy.SLIDING_WINDOW)
    assert res.allowed is True
    assert res.remaining == 99  # max_requests 100 - 0 - 1


@pytest.mark.asyncio
async def test_check_sliding_window_denied(rl):
    limiter, fake = rl
    fake.zcard_val = 100  # at/over limit
    res = await limiter.check("sw:k", "default", RateLimitStrategy.SLIDING_WINDOW)
    assert res.allowed is False
    assert res.remaining == 0


@pytest.mark.asyncio
async def test_check_fixed_window_allowed(rl):
    limiter, fake = rl
    fake.incr_val = 1
    res = await limiter.check("fw:k", "default", RateLimitStrategy.FIXED_WINDOW)
    assert res.allowed is True


@pytest.mark.asyncio
async def test_check_fixed_window_denied(rl):
    limiter, fake = rl
    fake.incr_val = 200  # exceeds default 100
    res = await limiter.check("fw:k", "default", RateLimitStrategy.FIXED_WINDOW)
    assert res.allowed is False


@pytest.mark.asyncio
async def test_check_token_bucket_allowed_and_denied(rl):
    limiter, fake = rl
    # allowed: tokens available
    fake.tokens = "50.0"
    fake.last_update = str(time.time() - 10)
    res = await limiter.check("tb:k", "default", RateLimitStrategy.TOKEN_BUCKET)
    assert res.allowed is True

    # denied: no tokens
    fake.tokens = "0.0"
    fake.last_update = str(time.time())
    res = await limiter.check("tb:k", "default", RateLimitStrategy.TOKEN_BUCKET)
    assert res.allowed is False


@pytest.mark.asyncio
async def test_login_brute_force_flow(rl):
    limiter, fake = rl
    ip, email = "1.2.3.4", "a@b.com"
    # not blocked initially
    assert await limiter.is_login_blocked(ip, email) is False
    # record failures
    await limiter.record_login_failure(ip, email)
    # force attempts over threshold and verify blocked
    fake.store[f"brute:ip:{ip}"] = 999
    assert await limiter.is_login_blocked(ip, email) is True
    # clear on success
    await limiter.clear_login_attempts(ip, email)
    assert fake.deleted
    assert await limiter.is_login_blocked(ip, email) is False


@pytest.mark.asyncio
async def test_login_blocked_disabled(rl, monkeypatch):
    from src.core import config
    limiter, _ = rl
    monkeypatch.setattr(config.rate_limit, "enabled", False)
    assert await limiter.is_login_blocked("1.1.1.1", "x@y.com") is False


@pytest.mark.asyncio
async def test_close_with_redis(rl):
    limiter, fake = rl
    fake.close = MagicMock()
    limiter._redis = fake
    await limiter.close()
    fake.close.assert_called_once()
