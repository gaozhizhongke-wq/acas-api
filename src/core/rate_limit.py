"""
ACAS v2 - Rate Limiting
Redis-backed sliding window with multiple strategies
Uses sync Redis client to avoid ProactorEventLoop issues on Windows
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

try:
    import redis  # Sync client
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from .config import config
from .logging import get_logger

logger = get_logger(__name__)

# Thread pool for sync Redis operations
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="redis-")


class RateLimitStrategy(Enum):
    """Rate limiting strategies"""
    FIXED_WINDOW = "fixed"
    SLIDING_WINDOW = "sliding"
    TOKEN_BUCKET = "token_bucket"


@dataclass
class RateLimitResult:
    """Rate limit check result"""
    allowed: bool
    remaining: int
    reset_time: int  # Unix timestamp
    retry_after: Optional[int] = None  # Seconds to wait


class RateLimiter:
    """Redis-backed rate limiter using sync client + thread pool"""
    
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._local_cache: dict = {}  # Fallback for testing
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def connect(self) -> None:
        """Connect to Redis"""
        if not config.rate_limit.enabled:
            logger.info("Rate limiting disabled by config")
            return
        
        try:
            # Sync Redis client — get_password() handles URL parsing + explicit field
            password = config.redis.get_password()
            self._redis = redis.Redis(
                host=config.redis.get_host(),
                port=config.redis.get_port(),
                password=password,
                db=config.redis.get_db(),
                socket_timeout=config.redis.socket_timeout or 5,
                socket_connect_timeout=config.redis.socket_connect_timeout or 5,
                retry_on_timeout=config.redis.retry_on_timeout or True,
                decode_responses=True
            )
            # Test connection
            self._redis.ping()
            logger.info("Rate limiter connected to Redis", extra={"host": config.redis.get_host()})
        except Exception as e:
            logger.error("Failed to connect to Redis", exc_info=e)
            self._redis = None
    
    async def close(self) -> None:
        """Close Redis connection"""
        if self._redis:
            self._redis.close()
    
    def _parse_limit(self, limit_str: str) -> Tuple[int, int]:
        """Parse 'count:window' format. Returns defaults on invalid input."""
        try:
            parts = limit_str.split(":")
            if len(parts) != 2:
                raise ValueError("Invalid format")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError, TypeError):
            return 100, 60  # defaults
    
    async def check(
        self,
        key: str,
        limit_type: str = "default",
        strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    ) -> RateLimitResult:
        """Check rate limit for key"""
        if not config.rate_limit.enabled or not self._redis:
            return RateLimitResult(allowed=True, remaining=999, reset_time=int(time.time()) + 60)
        
        # Get limit config
        limit_str = getattr(config.rate_limit, limit_type, config.rate_limit.default)
        max_requests, window = self._parse_limit(limit_str)
        
        if strategy == RateLimitStrategy.SLIDING_WINDOW:
            return await self._run_in_thread(self._sliding_window_sync, key, max_requests, window)
        elif strategy == RateLimitStrategy.FIXED_WINDOW:
            return await self._run_in_thread(self._fixed_window_sync, key, max_requests, window)
        else:
            return await self._run_in_thread(self._token_bucket_sync, key, max_requests, window)

    async def is_login_blocked(self, ip: str, email: str) -> bool:
        """Check if login attempts for this IP/email exceed the threshold"""
        if not config.rate_limit.enabled or not self._redis:
            return False

        limit_str = config.rate_limit.login
        max_attempts, window = self._parse_limit(limit_str)

        ip_key = f"brute:ip:{ip}"
        email_key = f"brute:email:{email}"

        return await self._run_in_thread(self._check_blocked_sync, ip_key, email_key, max_attempts)

    async def record_login_failure(self, ip: str, email: str) -> None:
        """Record a failed login attempt"""
        if not config.rate_limit.enabled or not self._redis:
            return

        _, window = self._parse_limit(config.rate_limit.login)
        ip_key = f"brute:ip:{ip}"
        email_key = f"brute:email:{email}"

        await self._run_in_thread(self._record_failure_sync, ip_key, email_key, window)

    async def clear_login_attempts(self, ip: str, email: str) -> None:
        """Clear login failure counters on successful login"""
        if not config.rate_limit.enabled or not self._redis:
            return

        await self._run_in_thread(
            self._clear_attempts_sync,
            f"brute:ip:{ip}",
            f"brute:email:{email}"
        )

    def _check_blocked_sync(self, ip_key: str, email_key: str, threshold: int) -> bool:
        """Check if either IP or email is blocked (sync)"""
        ip_attempts = int(self._redis.get(ip_key) or 0)
        if ip_attempts >= threshold:
            return True
        email_attempts = int(self._redis.get(email_key) or 0)
        return email_attempts >= threshold

    def _record_failure_sync(self, ip_key: str, email_key: str, window: int) -> None:
        """Record a failed login attempt (sync)"""
        pipe = self._redis.pipeline()
        pipe.incr(ip_key)
        pipe.expire(ip_key, window)
        pipe.incr(email_key)
        pipe.expire(email_key, window)
        pipe.execute()

    def _clear_attempts_sync(self, ip_key: str, email_key: str) -> None:
        """Clear failure counters on success (sync)"""
        self._redis.delete(ip_key, email_key)
    
    async def _run_in_thread(self, func, *args):
        """Run sync Redis operation in thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, func, *args)
    
    def _sliding_window_sync(self, key: str, max_requests: int, window: int) -> RateLimitResult:
        """Sliding window rate limit (sync)"""
        if self._redis is None:
            return RateLimitResult(allowed=True, remaining=max_requests, reset_time=0, retry_after=0)
        now = time.time()
        window_start = now - window
        
        # Remove old entries and add current request
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window)
        results = pipe.execute()
        
        current_count = results[1]  # Count before adding current
        
        if current_count >= max_requests:
            # Remove the request we just added
            self._redis.zrem(key, str(now))
            
            # Get oldest request in window for reset time
            oldest = self._redis.zrange(key, 0, 0, withscores=True)
            reset_time = int(oldest[0][1]) + window if oldest else int(now) + window
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=reset_time,
                retry_after=int(reset_time - now)
            )
        
        return RateLimitResult(
            allowed=True,
            remaining=max_requests - current_count - 1,
            reset_time=int(now) + window
        )
    
    def _fixed_window_sync(self, key: str, max_requests: int, window: int) -> RateLimitResult:
        """Fixed window rate limit (sync)"""
        if self._redis is None:
            return RateLimitResult(allowed=True, remaining=max_requests, reset_time=0, retry_after=0)
        now = int(time.time())
        window_key = f"{key}:{now // window}"
        
        pipe = self._redis.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, window)
        results = pipe.execute()
        
        current_count = results[0]
        reset_time = (now // window + 1) * window
        
        if current_count > max_requests:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=reset_time,
                retry_after=reset_time - now
            )
        
        return RateLimitResult(
            allowed=True,
            remaining=max_requests - current_count,
            reset_time=reset_time
        )
    
    def _token_bucket_sync(self, key: str, max_requests: int, window: int) -> RateLimitResult:
        """Token bucket rate limit (sync)"""
        if self._redis is None:
            return RateLimitResult(allowed=True, remaining=max_requests, reset_time=0, retry_after=0)
        tokens_key = f"{key}:tokens"
        last_update_key = f"{key}:last_update"
        
        now = time.time()
        rate = max_requests / window  # tokens per second
        
        pipe = self._redis.pipeline()
        pipe.get(tokens_key)
        pipe.get(last_update_key)
        results = pipe.execute()
        
        tokens = float(results[0]) if results[0] else max_requests
        last_update = float(results[1]) if results[1] else now
        
        # Add tokens based on time passed
        time_passed = now - last_update
        tokens = min(max_requests, tokens + time_passed * rate)
        
        if tokens >= 1:
            tokens -= 1
            allowed = True
        else:
            allowed = False
        
        # Save state
        pipe = self._redis.pipeline()
        pipe.setex(tokens_key, window, str(tokens))
        pipe.setex(last_update_key, window, str(now))
        pipe.execute()
        
        if allowed:
            return RateLimitResult(
                allowed=True,
                remaining=int(tokens),
                reset_time=int(now + (1 - tokens) / rate) if tokens < max_requests else int(now)
            )
        else:
            retry_after = int((1 - tokens) / rate) + 1
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=int(now + retry_after),
                retry_after=retry_after
            )


# Global instance
rate_limiter = RateLimiter()
