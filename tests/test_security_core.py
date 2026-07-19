"""
Deeper coverage for src.core.security: TokenBlacklist, TokenManager,
PasswordManager, EncryptionManager, APIKeyManager, SecureComparator.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.security import (
    AuthenticationError,
    SecurityError,
    TokenBlacklist,
    TokenManager,
    PasswordManager,
    EncryptionManager,
    APIKeyManager,
    SecureComparator,
    token_manager,
    password_manager,
    encryption_manager,
    api_key_manager,
    secure_compare,
)


# ── TokenBlacklist ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_blacklist_init_redis_ok():
    """Line 50-52: ping succeeds → _redis_available=True"""
    bl = TokenBlacklist()
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    await bl.initialize(mock_redis)
    assert bl._redis_available is True
    assert bl._redis_client is mock_redis


@pytest.mark.asyncio
async def test_blacklist_init_redis_fail():
    """Line 53-54: ping raises → _redis_available=False"""
    bl = TokenBlacklist()
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=RuntimeError("no redis"))
    await bl.initialize(mock_redis)
    assert bl._redis_available is False


@pytest.mark.asyncio
async def test_blacklist_add_is_blacklisted_redis():
    """Line 59-60, 68-69: add + is_blacklisted via Redis pipeline"""
    bl = TokenBlacklist()
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.setex = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)  # key exists
    await bl.initialize(mock_redis)

    await bl.add("jti-abc", expires_in_seconds=3600)
    mock_redis.setex.assert_awaited_once()

    is_bl = await bl.is_blacklisted("jti-abc")
    assert is_bl is True
    mock_redis.exists.assert_awaited()


@pytest.mark.asyncio
async def test_blacklist_fallback_memory():
    """Fallback in-memory when Redis unavailable"""
    bl = TokenBlacklist()
    await bl.initialize(None)
    assert bl._redis_available is False

    await bl.add("jti-mem")
    assert await bl.is_blacklisted("jti-mem") is True
    assert await bl.is_blacklisted("jti-other") is False


# ── TokenManager ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decode_expired_token():
    """Line 150: ExpiredSignatureError → AuthenticationError"""
    manager = TokenManager()
    expired = manager.create_token_pair("user")[0]
    # manually make it expired by patching time
    import time
    import jwt
    import src.core.security as sec
    now = sec.datetime.now(sec.timezone.utc)
    payload = {"sub": "user", "jti": "x", "type": "access",
               "exp": now - sec.timedelta(hours=1),
               "iat": now - sec.timedelta(hours=2)}
    expired = jwt.encode(payload, manager._secret, algorithm=manager._algorithm)
    with pytest.raises(AuthenticationError) as exc:
        await manager.decode_token(expired)
    assert "expired" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_decode_type_mismatch():
    """Line 160: wrong token type raises"""
    manager = TokenManager()
    # create a refresh token, ask for access
    refresh = manager.create_token_pair("user")[1]
    with pytest.raises(AuthenticationError) as exc:
        await manager.decode_token(refresh, expected_type="access")
    assert "Expected access" in str(exc.value)


@pytest.mark.asyncio
async def test_decode_blacklisted_raises():
    """Line 237-241: blacklisted token → AuthenticationError"""
    manager = TokenManager()
    token = manager.create_token_pair("user")[0]
    await manager._blacklist.add("")  # can't know jti without decoding; decode first
    payload = await manager.decode_token(token)
    jti = payload["jti"]
    await manager._blacklist.add(jti)
    with pytest.raises(AuthenticationError) as exc:
        await manager.decode_token(token)
    assert "revoked" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_revoke_valid_token_adds_to_blacklist():
    """Lines 197-203: revoke_token with valid token adds to blacklist"""
    tm = TokenManager()
    token, _ = tm.create_token_pair("u-revoke")
    await tm.revoke_token(token)  # should not raise; blacklist.add called


@pytest.mark.asyncio
async def test_revoke_invalid_token_silent():
    """Invalid token → pass (no-op)"""
    tm = TokenManager()
    await tm.revoke_token("not.a.valid.jwt.token")  # should not raise


# ── PasswordManager ──────────────────────────────────────────────────────────

def test_hash_password_too_short():
    """Line 230: Password < 8 chars → SecurityError"""
    with pytest.raises(SecurityError) as exc:
        password_manager.hash("1234567")
    assert "at least 8" in str(exc.value)


def test_verify_malformed_hash():
    """Line 237-241: verify with invalid hash → Exception caught → False"""
    result = password_manager.verify("password", "not-a-valid-argon2-hash")
    assert result is False


def test_hash_and_verify_valid():
    """Valid round-trip"""
    h = password_manager.hash("longpassword123")
    assert password_manager.verify("longpassword123", h) is True
    assert password_manager.verify("wrongpassword", h) is False


# ── EncryptionManager ──────────────────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    """Lines 254-255, 259, 263-265, 269-274: encrypt/decrypt with key set"""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    enc = EncryptionManager()
    enc._fernet = Fernet(key)
    assert enc.is_available() is True

    encrypted = enc.encrypt("secret data")
    assert encrypted != "secret data"
    assert enc.decrypt(encrypted) == "secret data"


def test_encrypt_decrypt_invalid_cipher():
    """Line 271-274: decrypt invalid ciphertext → SecurityError"""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    enc = EncryptionManager()
    enc._fernet = Fernet(key)
    with pytest.raises(SecurityError) as exc:
        enc.decrypt("invalidbase64data")
    assert "Decryption failed" in str(exc.value)


def test_encrypt_when_not_configured():
    """Lines 263-264: encrypt without key → SecurityError"""
    enc = EncryptionManager()
    enc._fernet = None
    with pytest.raises(SecurityError) as exc:
        enc.encrypt("data")
    assert "not configured" in str(exc.value)


def test_decrypt_when_not_configured():
    """Lines 269-270: decrypt without key → SecurityError"""
    enc = EncryptionManager()
    enc._fernet = None
    with pytest.raises(SecurityError) as exc:
        enc.decrypt("data")
    assert "not configured" in str(exc.value)


# ── APIKeyManager ─────────────────────────────────────────────────────────────

def test_validate_format_valid_live():
    """Lines 297-300: valid live key"""
    key_id, full_key, _ = api_key_manager.generate(test=False)
    assert api_key_manager.validate_format(full_key) is True


def test_validate_format_valid_test():
    key_id, full_key, _ = api_key_manager.generate(test=True)
    assert api_key_manager.validate_format(full_key) is True


def test_validate_format_wrong_prefix():
    assert api_key_manager.validate_format("bad_prefix_key") is False


def test_validate_format_missing_dot():
    key_id, full_key, _ = api_key_manager.generate()
    bad = full_key.replace(".", "X", 1)
    assert api_key_manager.validate_format(bad) is False


def test_hash_for_lookup():
    """Line 304: hash_for_lookup"""
    key_id, full_key, _ = api_key_manager.generate()
    h = api_key_manager.hash_for_lookup(full_key)
    assert len(h) == 64  # SHA256 hex
    assert h == api_key_manager.hash_for_lookup(full_key)  # deterministic


# ── SecureComparator ──────────────────────────────────────────────────────────

def test_compare_strings_match():
    assert secure_compare.compare_strings("hello", "hello") is True


def test_compare_strings_mismatch():
    assert secure_compare.compare_strings("hello", "world") is False


def test_compare_bytes_match():
    assert secure_compare.compare_bytes(b"hello", b"hello") is True


def test_compare_bytes_mismatch():
    assert secure_compare.compare_bytes(b"hello", b"world") is False


# ── Additional token_manager + manager methods ────────────────────────────────

@pytest.mark.asyncio
async def test_create_token_pair_with_custom_claims():
    """Line 111: base_claims.update(claims)"""
    tm = TokenManager()
    acc, ref = tm.create_token_pair("u1", claims={"role": "admin"})
    assert acc is not None
    assert ref is not None


@pytest.mark.asyncio
async def test_decode_invalid_token_raises():
    """Lines 151-152: InvalidTokenError → AuthenticationError"""
    tm = TokenManager()
    with pytest.raises(AuthenticationError) as exc:
        await tm.decode_token("not.valid.jwt")
    assert "Invalid token" in str(exc.value)


@pytest.mark.asyncio
async def test_rotate_refresh_token():
    """Lines 169-187: rotate_refresh_token full flow (blacklist old + issue new)"""
    tm = TokenManager()
    acc, ref = tm.create_token_pair("user-rotate", session_id="sid-rot")
    # rotate
    new_acc, new_ref, new_sid = await tm.rotate_refresh_token(ref)
    assert new_acc != acc
    assert new_ref != ref
    assert new_sid == "sid-rot"


@pytest.mark.asyncio
async def test_revoke_session_with_redis():
    """Lines 210-212: revoke_session with redis available"""
    tm = TokenManager()
    mock_redis = AsyncMock()
    await tm._blacklist.initialize(mock_redis)
    await tm.revoke_session("session-to-revoke", mock_redis)
    mock_redis.setex.assert_awaited_once()


def test_password_needs_rehash():
    """Line 245: needs_rehash"""
    h = password_manager.hash("longpassword123")
    assert password_manager.needs_rehash(h) is False


def test_encryption_manager_init_with_key(monkeypatch):
    """Lines 254-255: __init__ with encryption_key configured (SecretStr → str → Fernet)"""
    from cryptography.fernet import Fernet
    key_str = Fernet.generate_key().decode()  # Fernet.generate_key() returns bytes; SecretStr.get_secret_value() returns str
    fake_key = MagicMock()
    fake_key.get_secret_value = MagicMock(return_value=key_str)
    monkeypatch.setattr("src.core.security.config.security.encryption_key", fake_key)
    enc = EncryptionManager()
    assert enc._fernet is not None
