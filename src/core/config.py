"""
ACAS v2 - Configuration Management
Pydantic Settings with environment variable support
"""

import os
import secrets
from typing import Optional, List

from pydantic import Field, field_validator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecurityConfig(BaseSettings):
    """Security-related configuration"""

    model_config = SettingsConfigDict(env_prefix="ACAS_")

    secret_key: SecretStr = Field(
        default=SecretStr(secrets.token_urlsafe(32)),
        min_length=32,
        description="JWT secret key - MUST be set in production!"
    )
    encryption_key: Optional[SecretStr] = Field(
        default=None,
        description="Fernet key for data encryption"
    )

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)

    # Argon2 parameters
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost: int = Field(default=65536, ge=8192)
    argon2_parallelism: int = Field(default=4, ge=1)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: SecretStr) -> SecretStr:
        """Ensure secret key is not a default value in production"""
        value = v.get_secret_value()
        dangerous_patterns = [
            "change-me",
            "changeme",
            "secret",
            "password",
            "test",
            "dev",
            "development",
            "GENERATE",
        ]
        lower_value = value.lower()
        for pattern in dangerous_patterns:
            if pattern in lower_value:
                if os.getenv("ACAS_ENVIRONMENT", "development") == "production":
                    raise ValueError(
                        f"ACAS_SECRET_KEY contains insecure pattern '{pattern}'. "
                        "Generate a secure key: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                    )
        return v


class DatabaseConfig(BaseSettings):
    """Database configuration"""

    model_config = SettingsConfigDict(env_prefix="ACAS_DB_")

    url: str = Field(
        default="postgresql+psycopg://acas:acas@localhost:5432/acas",
        description="Database URL (psycopg sync driver)"
    )
    pool_size: int = Field(default=20, ge=1, le=100)
    max_overflow: int = Field(default=40, ge=0, le=100)
    echo: bool = Field(default=False)
    ssl_mode: str = Field(
        default="disable",
        description="SSL mode for database connection: disable, require, verify-ca, verify-full"
    )

    @property
    def sync_url(self) -> str:
        """Get sync URL for Alembic (psycopg is already sync)"""
        return self.url


class RedisConfig(BaseSettings):
    """Redis configuration"""

    model_config = SettingsConfigDict(env_prefix="ACAS_REDIS_")

    url: str = Field(default="redis://localhost:6379/0")
    host: Optional[str] = Field(default=None, description="Redis host (parsed from url if not set)")
    port: Optional[int] = Field(default=None, description="Redis port (parsed from url if not set)")
    db: Optional[int] = Field(default=None, description="Redis db (parsed from url if not set)")
    password: Optional[str] = None
    socket_timeout: int = Field(default=5, ge=1, le=30)
    socket_connect_timeout: int = Field(default=5, ge=1, le=30)
    retry_on_timeout: bool = Field(default=True)
    health_check_interval: int = Field(default=30, ge=5, le=300)

    def get_host(self) -> str:
        """Get Redis host"""
        if self.host:
            return self.host
        # Parse from url: redis://[:password@]host:port/db
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        return parsed.hostname or "localhost"

    def get_port(self) -> int:
        """Get Redis port"""
        if self.port:
            return self.port
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        return parsed.port or 6379

    def get_db(self) -> int:
        """Get Redis db"""
        if self.db is not None:
            return self.db
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        path = parsed.path.lstrip("/")
        return int(path) if path.isdigit() else 0

    def get_password(self) -> Optional[str]:
        """Get Redis password — from explicit field or parsed from URL."""
        if self.password:
            return self.password
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        return parsed.password if parsed.password else None


class APIConfig(BaseSettings):
    """API server configuration"""

    model_config = SettingsConfigDict(env_prefix="ACAS_API_")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    workers: int = Field(default=4, ge=1, le=32)
    reload: bool = Field(default=False)

    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated list of allowed CORS origins. In production, must be explicitly set."
    )
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: str = Field(default="GET,POST,PUT,PATCH,DELETE,OPTIONS")
    cors_allow_headers: str = Field(default="Authorization,Content-Type,X-Requested-With,X-Correlation-ID")

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into list"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


class RateLimitConfig(BaseSettings):
    """Rate limiting configuration"""

    model_config = SettingsConfigDict(env_prefix="ACAS_RL_")

    enabled: bool = Field(default=True)
    default: str = Field(default="100:60", description="requests:seconds")
    login: str = Field(default="5:300", description="5 requests per 5 minutes")
    register_limit: str = Field(default="3:3600", description="3 requests per hour")


class MLConfig(BaseSettings):
    """Machine learning configuration"""

    model_config = SettingsConfigDict(env_prefix="ACAS_ML_")

    timesfm_enabled: bool = Field(default=True)
    timesfm_model_path: Optional[str] = None
    timesfm_context_length: int = Field(default=512)
    timesfm_prediction_horizon: int = Field(default=96)
    sentiment_enabled: bool = Field(default=True)


class MonitoringConfig(BaseSettings):
    """Monitoring configuration"""

    model_config = SettingsConfigDict(env_prefix="ACAS_MON_")

    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")
    sentry_dsn: Optional[str] = None
    prometheus_enabled: bool = Field(default=True)


class AppConfig(BaseSettings):
    """Main application configuration"""

    model_config = SettingsConfigDict(
        env_prefix="ACAS_",
        env_nested_delimiter="__",
        extra="ignore",
        env_file=[".env", "../.env", "../../.env"],
        env_file_encoding="utf-8"
    )

    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    app_version: str = "2.0.0"
    app_name: str = "ACAS API"

    # Sub-configurations
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    ml: MLConfig = Field(default_factory=MLConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment == "development"


# Global config instance
config = AppConfig()
