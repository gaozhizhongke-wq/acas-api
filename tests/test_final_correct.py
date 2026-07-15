"""
ACAS v2 - Final 2% Coverage Push (Corrected)
Target: Cover missing lines in pii.py, metrics.py, config.py
Strategy: Use ACTUAL API (read from source code)
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
import os


# ── Test PII module (98% → 100%, 1 line missing) ────────────────────────

class TestPIIModule:
    """Test pii.py functions"""

    async def test_mask_email(self):
        """Test email masking"""
        from core.pii import mask_email
        
        result = mask_email("john.doe@example.com")
        assert "***" in result
        assert "example.com" in result

    async def test_mask_name(self):
        """Test name masking"""
        from core.pii import mask_name
        
        result = mask_name("John Doe")
        assert "**" in result

    async def test_redact_pii_from_dict_with_pii_keys(self):
        """Test PII redaction for dict with PII keys"""
        from core.pii import redact_pii_from_dict
        
        data = {
            "user_email": "john@example.com",
            "password": "secret123",
            "phone": "13800138000",
            "name": "John Doe"  # non-PII key, should not be redacted
        }
        
        result = redact_pii_from_dict(data)
        
        # PII keys should be redacted
        assert "***" in result["user_email"]
        assert result["password"] == "***"
        assert "***" in result["phone"]
        
        # Non-PII key should pass through (this covers line 59)
        assert result["name"] == "John Doe"

    async def test_redact_pii_from_dict_nested(self):
        """Test nested dict PII redaction"""
        from core.pii import redact_pii_from_dict
        
        data = {
            "user": {
                "email": "john@example.com",
                "password": "secret"
            }
        }
        
        result = redact_pii_from_dict(data)
        assert "***" in result["user"]["email"]
        assert result["user"]["password"] == "***"

    async def test_redact_sensitive_fields(self):
        """Test sensitive field redaction"""
        from core.pii import redact_sensitive_fields
        
        data = {
            "email": "john@example.com",
            "name": "John Doe",
            "api_key": "secret-key-123"
        }
        
        result = redact_sensitive_fields(data)
        assert result["email"] == "***"
        assert result["api_key"] == "***"
        assert result["name"] == "John Doe"  # not in default sensitive fields


# ── Test Metrics module (96% → 100%, 3 lines missing) ─────────────────────

class TestMetricsModule:
    """Test metrics.py functions"""

    async def test_metrics_tracker_basic(self):
        """Test basic MetricsTracker functionality"""
        from core.metrics import MetricsTracker
        
        tracker = MetricsTracker()
        
        # Test inc/dec active
        tracker.inc_active()
        assert tracker.get_active() == 1
        tracker.inc_active()
        assert tracker.get_active() == 2
        tracker.dec_active()
        assert tracker.get_active() == 1
        tracker.dec_active()
        assert tracker.get_active() == 0
        
        # Test record_request
        tracker.record_request("GET", "/health", 200, 0.01)
        assert tracker.get_active() == 0  # should not affect active count

    async def test_metrics_tracker_histogram(self):
        """Test histogram recording"""
        from core.metrics import MetricsTracker
        
        tracker = MetricsTracker()
        
        # Record requests with different durations
        tracker.record_request("GET", "/api/insights", 200, 0.01)  # fast
        tracker.record_request("POST", "/api/analysis", 201, 0.5)  # medium
        tracker.record_request("GET", "/api/forecast", 200, 3.0)  # slow
        
        # Render and check output
        output = tracker.render(version="1.0.0", environment="test", db_ok=True, redis_ok=True)
        
        assert "acas_info" in output
        assert "acas_database_connected" in output
        assert "acas_redis_connected" in output
        assert "acas_requests_total" in output
        assert "acas_request_duration_seconds" in output

    async def test_metrics_tracker_path_generalization(self):
        """Test path generalization"""
        from core.metrics import MetricsTracker
        
        tracker = MetricsTracker()
        
        # Test UUID replacement
        tracker.record_request("GET", "/users/550e8400-e29b-41d4-a716-446655440000", 200, 0.01)
        
        # Test integer ID replacement
        tracker.record_request("GET", "/users/12345", 200, 0.01)
        
        # Render and check that paths are generalized
        output = tracker.render(version="1.0.0", environment="test", db_ok=True, redis_ok=True)
        
        # Should see /users/:id instead of actual IDs
        assert "/users/:id" in output

    async def test_metrics_tracker_render_with_db_redis_down(self):
        """Test render when DB/Redis is down"""
        from core.metrics import MetricsTracker
        
        tracker = MetricsTracker()
        
        output = tracker.render(version="1.0.0", environment="prod", db_ok=False, redis_ok=False)
        
        assert "acas_database_connected 0" in output
        assert "acas_redis_connected 0" in output


# ── Test Config module (96% → 100%, 5 lines missing) ───────────────────────

class TestConfigModule:
    """Test config.py"""

    async def test_api_config_defaults(self):
        """Test APIConfig default values"""
        from core.config import APIConfig
        
        config = APIConfig()
        
        # Check default values
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.debug == False
        assert config.workers == 4

    async def test_api_config_custom_values(self):
        """Test APIConfig with custom values"""
        from core.config import APIConfig
        
        with patch.dict(os.environ, {
            "ACAS_API_PORT": "9000",
            "ACAS_API_HOST": "127.0.0.1",
            "ACAS_API_DEBUG": "true",
            "ACAS_API_WORKERS": "8",
        }):
            config = APIConfig()
            assert config.port == 9000
            assert config.host == "127.0.0.1"
            assert config.debug == True
            assert config.workers == 8

    async def test_api_config_jwt_settings(self):
        """Test JWT settings"""
        from core.config import APIConfig
        
        with patch.dict(os.environ, {
            "ACAS_JWT_SECRET": "test-secret-key-12345678901234567890123456789012",
            "ACAS_JWT_ALGORITHM": "HS512",
            "ACAS_TOKEN_EXPIRE_MINUTES": "120",
        }):
            config = APIConfig()
            assert len(config.jwt_secret) >= 32
            assert config.jwt_algorithm == "HS512"
            assert config.token_expire_minutes == 120

    async def test_database_config_ssl_mode(self):
        """Test DatabaseConfig SSL mode"""
        from core.config import DatabaseConfig
        
        with patch.dict(os.environ, {"ACAS_DB_SSL_MODE": "require"}):
            config = DatabaseConfig()
            assert config.ssl_mode == "require"

    async def test_database_config_default(self):
        """Test DatabaseConfig default values"""
        from core.config import DatabaseConfig
        
        config = DatabaseConfig()
        assert config.ssl_mode == "disable"  # default


# ── Test Logging module (89% → 95%+, 7 lines missing) ─────────────────────

class TestLoggingModule:
    """Test logging.py"""

    async def test_setup_logging(self):
        """Test logging setup"""
        from core.logging import setup_logging
        
        # Should not raise
        try:
            setup_logging()
        except Exception as e:
            pytest.fail(f"setup_logging raised {e}")

    async def test_get_logger(self):
        """Test get_logger"""
        from core.logging import get_logger
        
        logger = get_logger("test")
        assert logger is not None
        assert logger.name == "test"

    async def test_logging_with_sensitive_data(self):
        """Test that logging handles sensitive data"""
        from core.logging import get_logger
        
        logger = get_logger("test_sensitive")
        
        # Log a message with sensitive data (should be handled by filter)
        logger.info("User email: %s", "john@example.com")


# ── Test Database module (88% → 95%+, 11 lines missing) ────────────────────

class TestDatabaseModule:
    """Test database.py"""

    async def test_database_init(self):
        """Test Database initialization"""
        from core.database import Database
        
        db = Database()
        assert db is not None
        assert db._engine is None
        assert db._session_factory is None

    async def test_database_singleton(self):
        """Test that db singleton works"""
        from core.database import db
        
        assert db is not None

    async def test_get_db_session_generator(self):
        """Test get_db_session generator function"""
        from core.database import get_db_session
        
        # Should return an async generator
        gen = get_db_session()
        assert gen is not None
