"""
ACAS v2 - Config Coverage Tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import patch


class TestConfig:
    """Test configuration loading and properties"""

    def test_default_values(self):
        """test_default_values - config loads with defaults"""
        from src.core.config import AppConfig

        # Create fresh config (not global)
        cfg = AppConfig()

        assert cfg.app_name == "ACAS API"
        assert cfg.app_version == "2.0.0"
        assert cfg.environment == "development"
        assert cfg.debug is False
        assert cfg.database.pool_size == 20
        assert cfg.database.max_overflow == 40
        assert cfg.database.echo is False
        assert cfg.redis.socket_timeout == 5

    def test_ssl_mode_default(self):
        """SSL mode defaults to 'disable'"""
        from src.core.config import DatabaseConfig

        cfg = DatabaseConfig()
        assert cfg.ssl_mode == "disable"

    def test_ssl_mode_custom(self):
        """SSL mode can be set to require"""
        from src.core.config import DatabaseConfig

        cfg = DatabaseConfig(url="postgresql+psycopg://u:p@h/d", ssl_mode="require")
        assert cfg.ssl_mode == "require"

    def test_is_production(self):
        """test_is_production - environment check"""
        from src.core.config import AppConfig

        prod_cfg = AppConfig(environment="production")
        assert prod_cfg.is_production is True
        assert prod_cfg.is_development is False

        dev_cfg = AppConfig(environment="development")
        assert dev_cfg.is_production is False
        assert dev_cfg.is_development is True

        staging_cfg = AppConfig(environment="staging")
        assert staging_cfg.is_production is False

    def test_cors_origins_list(self):
        """test_cors_origins_list - parse comma-separated"""
        from src.core.config import APIConfig

        cfg = APIConfig(cors_origins="http://localhost:3000,http://localhost:5173,https://example.com")
        origins = cfg.cors_origins_list

        assert len(origins) == 3
        assert "http://localhost:3000" in origins
        assert "http://localhost:5173" in origins
        assert "https://example.com" in origins

    def test_cors_origins_list_with_spaces(self):
        """cors_origins_list strips whitespace"""
        from src.core.config import APIConfig

        cfg = APIConfig(cors_origins="  http://a.com  ,  http://b.com ")
        origins = cfg.cors_origins_list

        assert "http://a.com" in origins
        assert "http://b.com" in origins

    def test_cors_origins_empty(self):
        """Empty cors_origins returns empty list"""
        from src.core.config import APIConfig

        cfg = APIConfig(cors_origins="")
        assert cfg.cors_origins_list == []

    def test_rate_limit_defaults(self):
        """Rate limit config has sensible defaults"""
        from src.core.config import RateLimitConfig

        cfg = RateLimitConfig()
        assert cfg.enabled is True
        assert cfg.default == "100:60"
        assert cfg.login == "5:300"

    def test_rate_limit_disabled(self):
        """Rate limit can be disabled"""
        from src.core.config import RateLimitConfig

        cfg = RateLimitConfig(enabled=False)
        assert cfg.enabled is False

    def test_redis_get_host(self):
        """Redis host is parsed from URL correctly"""
        from src.core.config import RedisConfig

        cfg = RedisConfig(url="redis://:mypassword@myhost:6380/5")
        assert cfg.get_host() == "myhost"
        assert cfg.get_port() == 6380
        assert cfg.get_db() == 5

    def test_redis_get_password_from_url(self):
        """Redis password is parsed from URL"""
        from src.core.config import RedisConfig

        cfg = RedisConfig(url="redis://:mypassword@myhost:6379/0")
        assert cfg.get_password() == "mypassword"

    def test_redis_get_password_explicit(self):
        """Explicit Redis password takes precedence over URL"""
        from src.core.config import RedisConfig

        cfg = RedisConfig(url="redis://:urlpass@host/0", password="explicit")
        assert cfg.get_password() == "explicit"

    def test_redis_get_password_none(self):
        """Redis password returns None when not set"""
        from src.core.config import RedisConfig

        cfg = RedisConfig(url="redis://localhost/0")
        assert cfg.get_password() is None

    def test_database_sync_url(self):
        """Database sync_url returns the same URL (psycopg is already sync)"""
        from src.core.config import DatabaseConfig

        url = "postgresql+psycopg://u:p@h/d"
        cfg = DatabaseConfig(url=url)
        assert cfg.sync_url == url

    def test_security_secret_key_auto_generated(self):
        """Secret key is auto-generated if not set"""
        from src.core.config import SecurityConfig

        cfg = SecurityConfig()
        key_value = cfg.secret_key.get_secret_value()
        assert len(key_value) >= 32

    def test_ml_sentiment_enabled_default(self, monkeypatch):
        """ML sentiment enabled by default"""
        monkeypatch.delenv("ACAS_ML_SENTIMENT_ENABLED", raising=False)
        monkeypatch.delenv("ACAS_ML_TIMESFM_ENABLED", raising=False)
        from src.core.config import MLConfig

        cfg = MLConfig()
        assert cfg.sentiment_enabled is True
        assert cfg.timesfm_enabled is True

    def test_monitoring_log_level(self):
        """Monitoring config has correct defaults"""
        from src.core.config import MonitoringConfig

        cfg = MonitoringConfig()
        assert cfg.log_level == "INFO"
        assert cfg.log_format == "json"
        assert cfg.prometheus_enabled is True

    def test_app_config_nested(self):
        """AppConfig properly nests sub-configs"""
        from src.core.config import AppConfig

        cfg = AppConfig()
        assert cfg.security is not None
        assert cfg.database is not None
        assert cfg.redis is not None
        assert cfg.api is not None
        assert cfg.rate_limit is not None
        assert cfg.ml is not None
        assert cfg.monitoring is not None
