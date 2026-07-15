"""
ACAS v2 - Logging Coverage Tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import json
import logging
import pytest
from unittest.mock import patch


class TestLogging:
    """Test logging utilities"""

    def test_json_formatter_basic(self):
        """test_json_formatter_basic - format creates valid JSON"""
        from src.core.logging import JSONFormatter

        class MockRecord(logging.LogRecord):
            def __init__(self):
                super().__init__(
                    name="test", level=logging.INFO, pathname="/fake/path.py",
                    lineno=10, msg="hello", args=(), exc_info=None
                )

        record = MockRecord()
        formatter = JSONFormatter()

        with patch("src.core.logging.config") as mock_config:
            mock_config.is_development = False
            output = formatter.format(record)

        parsed = json.loads(output)
        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello"
        assert parsed["logger"] == "test"

    def test_json_formatter_includes_correlation_id(self):
        """JSON formatter includes correlation_id from record"""
        from src.core.logging import JSONFormatter

        class MockRecord(logging.LogRecord):
            def __init__(self):
                super().__init__(
                    name="test", level=logging.INFO, pathname="/fake/path.py",
                    lineno=10, msg="hello", args=(), exc_info=None
                )
                self.correlation_id = "abc12345"

        record = MockRecord()
        formatter = JSONFormatter()

        with patch("src.core.logging.config") as mock_config:
            mock_config.is_development = False
            output = formatter.format(record)

        parsed = json.loads(output)
        assert parsed["correlation_id"] == "abc12345"

    def test_json_formatter_redact(self):
        """test_json_formatter_redact - SENSITIVE_FIELDS are redacted"""
        from src.core.logging import JSONFormatter

        class MockRecord(logging.LogRecord):
            def __init__(self):
                super().__init__(
                    name="test", level=logging.INFO, pathname="/fake/path.py",
                    lineno=10, msg="login", args=(), exc_info=None
                )
                self.extra = {
                    "password": "supersecret",
                    "email": "user@example.com",
                    "api_key": "secret-key-123",
                    "user": "john_doe",  # not sensitive
                }

        record = MockRecord()
        formatter = JSONFormatter()

        with patch("src.core.logging.config") as mock_config:
            mock_config.is_development = False
            output = formatter.format(record)

        parsed = json.loads(output)
        extra = parsed["extra"]

        assert extra["password"] == "***REDACTED***"
        assert extra["api_key"] == "***REDACTED***"
        # email is in SENSITIVE_FIELDS → redacted
        assert extra["email"] == "***REDACTED***"
        # user is not sensitive → should pass through
        assert extra["user"] == "john_doe"

    def test_json_formatter_redact_nested(self):
        """Sensitive fields are redacted in nested dicts"""
        from src.core.logging import JSONFormatter

        class MockRecord(logging.LogRecord):
            def __init__(self):
                super().__init__(
                    name="test", level=logging.INFO, pathname="/fake/path.py",
                    lineno=10, msg="login", args=(), exc_info=None
                )
                self.extra = {
                    "request": {
                        "password": "secret123",
                        "token": "abc",
                    }
                }

        record = MockRecord()
        formatter = JSONFormatter()

        with patch("src.core.logging.config") as mock_config:
            mock_config.is_development = False
            output = formatter.format(record)

        parsed = json.loads(output)
        request_extra = parsed["extra"]["request"]
        assert request_extra["password"] == "***REDACTED***"
        assert request_extra["token"] == "***REDACTED***"

    def test_correlation_id_filter(self):
        """test_correlation_id_filter - filter adds correlation_id"""
        from src.core.logging import CorrelationIdFilter

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="/fake/path.py",
            lineno=10, msg="hello", args=(), exc_info=None
        )

        filt = CorrelationIdFilter()
        result = filt.filter(record)

        assert result is True
        assert hasattr(record, "correlation_id")
        assert len(record.correlation_id) == 8  # uuid[:8]
        assert hasattr(record, "request_id")
        assert hasattr(record, "user_id")

    def test_correlation_id_filter_preserves_existing(self):
        """Filter preserves existing correlation_id"""
        from src.core.logging import CorrelationIdFilter

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="/fake/path.py",
            lineno=10, msg="hello", args=(), exc_info=None
        )
        record.correlation_id = "existing-id"
        record.request_id = "req-001"
        record.user_id = "user-123"

        filt = CorrelationIdFilter()
        result = filt.filter(record)

        assert result is True
        assert record.correlation_id == "existing-id"
        assert record.request_id == "req-001"
        assert record.user_id == "user-123"

    def test_text_formatter(self):
        """TextFormatter produces readable output"""
        from src.core.logging import TextFormatter

        class MockRecord(logging.LogRecord):
            def __init__(self):
                super().__init__(
                    name="test", level=logging.INFO, pathname="/fake/path.py",
                    lineno=10, msg="hello world", args=(), exc_info=None
                )
                self.correlation_id = "abc12345"

        record = MockRecord()
        formatter = TextFormatter()
        output = formatter.format(record)

        assert "INFO" in output
        assert "abc12345" in output
        assert "hello world" in output

    def test_get_logger(self):
        """get_logger returns a logger instance"""
        from src.core.logging import get_logger
        logger = get_logger("test-module")
        assert logger is not None
        assert logger.name == "test-module"
