"""
ACAS v2 - Enterprise Security Layer
Argon2 password hashing, JWT with rotation, Fernet encryption, Token blacklist
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, Set

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from .config import config


class SecurityError(Exception):
    """Security-related errors"""
    pass


class AuthenticationError(SecurityError):
    """Authentication failed"""
    pass


class AuthorizationError(SecurityError):
    """Authorization failed"""
    pass


class TokenBlacklist:
    """
    Token blacklist for logout and refresh token invalidation
    Uses Redis in production, falls back to in-memory for development
    """

    def __init__(self):
        self._blacklist: Set[str] = set()
        self._redis_client = None
        self._redis_available = False

    async def initialize(self, redis_client=None) -> None:
        """Initialize with Redis client if available"""
        self._redis_client = redis_client
        if redis_client:
            try:
                await redis_client.ping()
                self._redis_available = True
            except Exception:
                self._redis_available = False

    async def add(self, jti: str, expires_in_seconds: int = 86400 * 7) -> None:
        """Add token to blacklist"""
        if self._redis_available and self._redis_client:
            key = f"blacklist:{jti}"
            await self._redis_client.setex(key, expires_in_seconds, "1")
        else:
            # Fallback to in-memory (not persistent across restarts)
            self._blacklist.add(jti)

    async def is_blacklisted(self, jti: str) -> bool:
        """Check if token is blacklisted"""
        if self._redis_available and self._redis_client:
            key = f"blacklist:{jti}"
            return await self._redis_client.exists(key) > 0
        else:
            return jti in self._blacklist

    async def remove_expired(self) -> None:
        """Clean up expired tokens (Redis handles this automatically)"""
        # In-memory cleanup would need timestamp tracking
        # For simplicity, we rely on Redis TTL in production
        pass


class TokenManager:
    """JWT token management with refresh rotation"""

    def __init__(self):
        self._secret = config.security.secret_key.get_secret_value()
        self._algorithm = config.security.jwt_algorithm
        self._blacklist = TokenBlacklist()

    async def initialize(self, redis_client=None) -> None:
        """Initialize token blacklist"""
        await self._blacklist.initialize(redis_client)

    def create_token_pair(
        self,
        user_id: str,
        claims: Optional[Dict] = None,
        session_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """Create access + refresh token pair"""
        now = datetime.now(timezone.utc)
        jti = secrets.token_urlsafe(16)
        session_id = session_id or str(uuid.uuid4())

        base_claims = {
            "sub": user_id,
            "jti": jti,
            "sid": session_id,
            "type": "access",
            "iat": now,
        }
        if claims:
            base_claims.update(claims)

        # Access token
        access_claims = base_claims.copy()
        access_claims["exp"] = now + timedelta(
            minutes=config.security.access_token_expire_minutes
        )
        access_token = jwt.encode(
            access_claims, self._secret, algorithm=self._algorithm
        )

        # Refresh token
        refresh_claims = {
            "sub": user_id,
            "jti": secrets.token_urlsafe(16),
            "sid": session_id,
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=config.security.refresh_token_expire_days)
        }
        refresh_token = jwt.encode(
            refresh_claims, self._secret, algorithm=self._algorithm
        )

        return access_token, refresh_token

    async def decode_token(
        self,
        token: str,
        expected_type: Optional[str] = None
    ) -> Dict:
        """Decode and validate token"""
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm]
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")

        # Check blacklist
        jti = payload.get("jti")
        if jti and await self._blacklist.is_blacklisted(jti):
            raise AuthenticationError("Token has been revoked")

        if expected_type and payload.get("type") != expected_type:
            raise AuthenticationError(f"Expected {expected_type} token")

        return payload

    async def rotate_refresh_token(
        self,
        refresh_token: str
    ) -> Tuple[str, str, str]:
        """Rotate refresh token - invalidates old one, returns new pair + session_id"""
        payload = await self.decode_token(refresh_token, expected_type="refresh")
        user_id = payload["sub"]
        session_id = payload["sid"]
        old_jti = payload.get("jti")

        # Blacklist old refresh token
        if old_jti:
            # Calculate remaining TTL for blacklist
            exp = payload.get("exp", 0)
            now = datetime.now(timezone.utc).timestamp()
            ttl = max(1, int(exp - now))
            await self._blacklist.add(old_jti, ttl)

        # Create new pair
        access_token, new_refresh = self.create_token_pair(
            user_id, session_id=session_id
        )

        return access_token, new_refresh, session_id

    async def revoke_token(self, token: str) -> None:
        """Revoke a token (add to blacklist)"""
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm]
            )
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            now = datetime.now(timezone.utc).timestamp()
            ttl = max(1, int(exp - now))

            if jti:
                await self._blacklist.add(jti, ttl)
        except jwt.InvalidTokenError:
            pass  # Already invalid, nothing to revoke

    async def revoke_session(self, session_id: str, redis_client=None) -> None:
        """Revoke all tokens in a session"""
        # Store session ID in blacklist
        key = f"session_revoked:{session_id}"
        if self._blacklist._redis_available and self._blacklist._redis_client:
            await self._blacklist._redis_client.setex(key, 86400 * 30, "1")


class PasswordManager:
    """Argon2 password hashing"""

    def __init__(self):
        self._ctx = CryptContext(
            schemes=["argon2"],
            deprecated="auto",
            argon2__time_cost=config.security.argon2_time_cost,
            argon2__memory_cost=config.security.argon2_memory_cost,
            argon2__parallelism=config.security.argon2_parallelism,
        )

    def hash(self, password: str) -> str:
        """Hash password"""
        if len(password) < 8:
            raise SecurityError("Password must be at least 8 characters")
        return self._ctx.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        """Verify password"""
        try:
            return self._ctx.verify(password, hashed)
        except Exception:
            # Constant time comparison to prevent timing attacks
            dummy_hash = self._ctx.hash("dummy")
            self._ctx.verify("dummy", dummy_hash)
            return False

    def needs_rehash(self, hashed: str) -> bool:
        """Check if password needs rehashing"""
        return self._ctx.needs_update(hashed)


class EncryptionManager:
    """Fernet symmetric encryption for sensitive data"""

    def __init__(self):
        self._fernet: Optional[Fernet] = None
        if config.security.encryption_key:
            key = config.security.encryption_key.get_secret_value()
            self._fernet = Fernet(key.encode())

    def is_available(self) -> bool:
        """Check if encryption is configured"""
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        """Encrypt string, returns base64"""
        if not self._fernet:
            raise SecurityError("Encryption not configured")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64 string"""
        if not self._fernet:
            raise SecurityError("Encryption not configured")
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise SecurityError("Decryption failed - invalid or corrupted data")


class APIKeyManager:
    """API key generation and validation"""

    PREFIX = "ak_live_"
    PREFIX_TEST = "ak_test_"

    def generate(self, test: bool = False) -> Tuple[str, str, str]:
        """Generate API key - returns (key_id, full_key, key_hash)"""
        key_id = secrets.token_urlsafe(16)
        secret = secrets.token_urlsafe(32)
        prefix = self.PREFIX_TEST if test else self.PREFIX
        full_key = f"{prefix}{key_id}.{secret}"

        # Hash for storage
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()

        return key_id, full_key, key_hash

    def validate_format(self, key: str) -> bool:
        """Validate API key format"""
        if not key.startswith((self.PREFIX, self.PREFIX_TEST)):
            return False
        parts = key[len(self.PREFIX):].split(".")
        return len(parts) == 2 and all(len(p) > 0 for p in parts)

    def hash_for_lookup(self, key: str) -> str:
        """Get hash for database lookup"""
        return hashlib.sha256(key.encode()).hexdigest()


class SecureComparator:
    """Constant-time comparison utilities"""

    @staticmethod
    def compare_strings(a: str, b: str) -> bool:
        """Constant-time string comparison"""
        return hmac.compare_digest(a.encode(), b.encode())

    @staticmethod
    def compare_bytes(a: bytes, b: bytes) -> bool:
        """Constant-time bytes comparison"""
        return hmac.compare_digest(a, b)


# Global instances
token_manager = TokenManager()
password_manager = PasswordManager()
encryption_manager = EncryptionManager()
api_key_manager = APIKeyManager()
secure_compare = SecureComparator()
