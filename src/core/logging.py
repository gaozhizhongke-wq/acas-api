"""
ACAS v2 - Structured Logging
JSON format for production, correlation IDs, PII redaction
"""

import json
import logging
import logging.config
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from .config import config


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Get from context or generate new
        record.correlation_id = getattr(record, "correlation_id", str(uuid.uuid4())[:8])
        record.request_id = getattr(record, "request_id", "-")
        record.user_id = getattr(record, "user_id", "-")
        return True


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging"""
    
    # Fields that might contain PII - redact these
    SENSITIVE_FIELDS = {
        "password", "passwd", "pwd", "secret", "token",
        "api_key", "apikey", "authorization", "cookie",
        "credit_card", "ssn", "email", "phone",
        "ip", "ip_address", "client_ip", "remote_addr"
    }
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
        }
        
        # Add source location for debugging
        if config.is_development:
            log_obj["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName
            }
        
        # Add exception info
        if record.exc_info:
            log_obj["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields with PII redaction
        if hasattr(record, "extra"):
            log_obj["extra"] = self._redact_sensitive(record.extra)
        
        return json.dumps(log_obj, default=str, ensure_ascii=False)
    
    def _redact_sensitive(self, data: Any) -> Any:
        """Recursively redact sensitive fields"""
        if isinstance(data, dict):
            return {
                k: "***REDACTED***" if self._is_sensitive(k) else self._redact_sensitive(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._redact_sensitive(item) for item in data]
        return data
    
    def _is_sensitive(self, field_name: str) -> bool:
        """Check if field name indicates sensitive data"""
        field_lower = field_name.lower()
        return any(s in field_lower for s in self.SENSITIVE_FIELDS)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter for development"""
    
    def format(self, record: logging.LogRecord) -> str:
        record.correlation_id = getattr(record, "correlation_id", "-")
        fmt = "%(asctime)s [%(levelname)s] %(correlation_id)s %(name)s: %(message)s"
        self._fmt = fmt
        self._style = logging.PercentStyle(fmt)
        return super().format(record)


def setup_logging() -> None:
    """Configure logging"""
    log_config = config.monitoring
    
    formatter_class = JSONFormatter if log_config.log_format == "json" else TextFormatter
    
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "correlation_id": {
                "()": CorrelationIdFilter
            }
        },
        "formatters": {
            "default": {
                "()": formatter_class
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "default",
                "filters": ["correlation_id"],
                "level": log_config.log_level
            }
        },
        "root": {
            "handlers": ["console"],
            "level": log_config.log_level
        },
        "loggers": {
            "uvicorn": {"level": "WARNING"},
            "sqlalchemy.engine": {"level": "WARNING" if not config.database.echo else "DEBUG"},
            "httpx": {"level": "WARNING"}
        }
    }
    
    logging.config.dictConfig(logging_config)


def get_logger(name: str) -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter with context"""
    
    def __init__(
        self,
        logger: logging.Logger,
        correlation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        super().__init__(logger, {})
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.request_id = request_id or "-"
        self.user_id = user_id or "-"
    
    def process(self, msg: str, kwargs: Any) -> tuple:
        """Add context to log record"""
        extra = kwargs.get("extra", {})
        extra["correlation_id"] = self.correlation_id
        extra["request_id"] = self.request_id
        extra["user_id"] = self.user_id
        kwargs["extra"] = extra
        return msg, kwargs
