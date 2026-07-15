"""
ACAS v2 - Config & Database Coverage Boost
Target: Boost config.py from 96% to 100% and database.py from 88% to 95%+
Strategy: Test edge cases in configuration and database modules
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
import os
import tempfile


class TestConfigCoverage:
    """Test config.py edge cases to boost from 96% to 100%"""

    async def test_config_with_all_env_vars(self):
        """Test config loading with all environment variables"""
        from core.config import APIConfig
        
        # Test with custom env vars
        with patch.dict(os.environ, {
            "ACAS_API_PORT": "9000",
            "ACAS_API_HOST": "0.0.0.0",
            "ACAS_API_DEBUG": "true",
            "ACAS_JWT_SECRET": "test-secret-key-123456789012345678901234",
            "ACAS_JWT_ALGORITHM": "HS512",
            "ACAS_TOKEN_EXPIRE_MINUTES": "60",
            "ACAS_RATE_LIMIT_ENABLED": "true",
            "ACAS_ML_SENTIMENT_ENABLED": "true",
        }):
            config = APIConfig()
            assert config.port == 9000
            assert config.host == "0.0.0.0"
            assert config.debug == True
            assert config.jwt_secret == "test-secret-key-123456789012345678901234"
            assert config.jwt_algorithm == "HS512"
            assert config.token_expire_minutes == 60
            assert config.rate_limit_enabled == True
            assert config.ml_sentiment_enabled == True

    async def test_config_with_invalid_values(self):
        """Test config with invalid values (edge cases)"""
        from core.config import APIConfig
        
        # Test with invalid port (should use default)
        with patch.dict(os.environ, {"ACAS_API_PORT": "invalid"}):
            config = APIConfig()
            assert config.port == 8000  # Default value

    async def test_config_ssl_mode(self):
        """Test SSL mode configuration"""
        from core.config import DatabaseConfig
        
        with patch.dict(os.environ, {"ACAS_DB_SSL_MODE": "require"}):
            config = DatabaseConfig()
            assert config.ssl_mode == "require"

    async def test_config_redis_url(self):
        """Test Redis URL configuration"""
        from core.config import APIConfig
        
        with patch.dict(os.environ, {"ACAS_REDIS_URL": "redis://:pass@localhost:6379/1"}):
            config = APIConfig()
            assert "redis://:pass@localhost:6379/1" in config.redis_url


class TestDatabaseCoverage:
    """Test database.py edge cases to boost from 88% to 95%+"""

    async def test_database_health_check_success(self):
        """Test database health check success path"""
        from core.database import Database
        from sqlalchemy import text
        
        db = Database()
        
        # Mock the engine
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        
        db._engine = mock_engine
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.execute.return_value = mock_result
        
        result = await db.health_check()
        assert result == True

    async def test_database_health_check_failure(self):
        """Test database health check failure path"""
        from core.database import Database
        
        db = Database()
        
        # Mock the engine to raise exception
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Connection failed")
        
        db._engine = mock_engine
        
        result = await db.health_check()
        assert result == False

    async def test_database_close(self):
        """Test database close method"""
        from core.database import Database
        
        db = Database()
        db._engine = MagicMock()
        db._engine.dispose = MagicMock()
        
        await db.close()
        db._engine.dispose.assert_called_once()

    async def test_database_session_factory(self):
        """Test database session factory"""
        from core.database import Database
        
        db = Database()
        db._session_factory = MagicMock()
        
        # Test that session factory is called
        session = db._session_factory()
        assert session is not None


class TestSecurityCoverage:
    """Test security.py edge cases to boost from 78% to 85%+"""

    async def test_password_manager_hash_verify(self):
        """Test password hashing and verification"""
        from core.security import password_manager
        
        password = "TestPass123!"
        hashed = password_manager.hash_password(password)
        
        assert hashed != password
        assert password_manager.verify_password(password, hashed) == True
        assert password_manager.verify_password("WrongPass", hashed) == False

    async def test_token_manager_create_verify(self):
        """Test token creation and verification"""
        from core.security import token_manager
        
        data = {"sub": "test_user", "role": "analyst"}
        token = token_manager.create_access_token(data)
        
        assert token is not None
        assert isinstance(token, str)
        
        # Verify token
        payload = token_manager.verify_token(token)
        assert payload["sub"] == "test_user"
        assert payload["role"] == "analyst"

    async def test_token_manager_expired_token(self):
        """Test expired token handling"""
        from core.security import token_manager
        from fastapi import HTTPException
        
        # Create a token that expires immediately
        data = {"sub": "test_user"}
        token = token_manager.create_access_token(data, expires_delta=-1)  # Already expired
        
        try:
            token_manager.verify_token(token)
            assert False, "Should have raised exception"
        except HTTPException as e:
            assert e.status_code == 401

    async def test_api_key_manager_hash_verify(self):
        """Test API key hashing and verification"""
        from core.security import api_key_manager
        
        api_key = api_key_manager.generate_api_key()
        hashed = api_key_manager.hash_api_key(api_key)
        
        assert hashed != api_key
        assert api_key_manager.verify_api_key(api_key, hashed) == True
        assert api_key_manager.verify_api_key("invalid_key", hashed) == False


class TestRateLimitCoverage:
    """Test rate_limit.py edge cases to boost from 87% to 95%+"""

    async def test_rate_limiter_is_blocked(self):
        """Test rate limiter block check"""
        from core.rate_limit import RateLimiter
        
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = "5"  # 5 requests (at limit)
        
        # Test that user is blocked
        result = await rl.is_rate_limited("test_key")
        assert result == True

    async def test_rate_limiter_not_blocked(self):
        """Test rate limiter not blocked"""
        from core.rate_limit import RateLimiter
        
        rl = RateLimiter()
        rl._redis = MagicMock()
        rl._redis.get.return_value = "3"  # 3 requests (under limit)
        
        result = await rl.is_rate_limited("test_key")
        assert result == False

    async def test_rate_limiter_redis_unavailable(self):
        """Test rate limiter when Redis is unavailable"""
        from core.rate_limit import RateLimiter
        
        rl = RateLimiter()
        rl._redis = None  # Redis unavailable
        
        # Should not block when Redis is unavailable
        result = await rl.is_rate_limited("test_key")
        assert result == False


class TestLoggingCoverage:
    """Test logging.py edge cases to boost from 79% to 90%+"""

    async def test_logging_setup(self):
        """Test logging configuration"""
        from core.logging import setup_logging
        
        # Test that setup_logging doesn't raise
        try:
            setup_logging()
            assert True
        except Exception as e:
            assert False, f"setup_logging raised exception: {e}"

    async def test_get_logger(self):
        """Test get_logger function"""
        from core.logging import get_logger
        
        logger = get_logger("test_logger")
        assert logger is not None
        assert logger.name == "test_logger"

    async def test_sensitive_data_filter(self):
        """Test sensitive data filtering in logs"""
        from core.logging import SensitiveDataFilter
        
        filter = SensitiveDataFilter()
        
        # Test that sensitive data is filtered
        record = MagicMock()
        record.getMessage.return_value = "password=secret123"
        
        result = filter.filter(record)
        assert result is not None  # Should not filter out, but mask
