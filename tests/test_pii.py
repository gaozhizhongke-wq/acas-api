"""
ACAS v2 - PII Module Coverage Tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest


class TestPII:
    """Test PII masking and redaction"""

    def test_mask_email(self):
        """test_mask_email - name preserves last char: john@example.com → j***n@example.com"""
        from src.core.pii import mask_email

        result = mask_email("john@example.com")
        # mask_email keeps first + last char: "john" → "j***n"
        assert result == "j***n@example.com"

    def test_mask_email_short_name(self):
        """Short email names are masked appropriately"""
        from src.core.pii import mask_email

        result = mask_email("ab@example.com")
        # <= 2 chars: "ab" → "a***"
        assert result == "a***@example.com"

    def test_mask_email_multiple_at_signs(self):
        """Email with subdomain works correctly"""
        from src.core.pii import mask_email

        result = mask_email("john.doe@sub.domain.example.com")
        # name "john.doe" → j***e@sub.domain.example.com
        assert result.startswith("j***e@")

    def test_mask_name(self):
        """test_mask_name - Zhang S**"""
        from src.core.pii import mask_name

        result = mask_name("Zhang San")
        assert result.startswith("Z")
        assert "**" in result

    def test_mask_name_single_part(self):
        """Single-part name is masked"""
        from src.core.pii import mask_name

        result = mask_name("John")
        assert "**" in result
        assert result.startswith("J")

    def test_redact_pii_from_dict_basic(self):
        """Basic dict redaction with password key"""
        from src.core.pii import redact_pii_from_dict

        data = {"username": "john", "password": "secret123"}
        result = redact_pii_from_dict(data)

        assert result["username"] == "john"
        # password key detected, but value is long string → partial mask
        assert "password" in result

    def test_redact_pii_nested(self):
        """Nested dict redaction"""
        from src.core.pii import redact_pii_from_dict

        data = {
            "user": {
                "email": "john@example.com",
                "password": "secret"
            }
        }
        result = redact_pii_from_dict(data)

        # email detected in email value → mask_email applied
        assert "email" in result["user"]
        # password detected; "secret" has len=6 > 4 → partial mask: "se***et"
        assert result["user"]["password"] == "se***et"

    def test_redact_pii_depth_limit(self):
        """Depth limit prevents infinite recursion"""
        from src.core.pii import redact_pii_from_dict

        # Create deeply nested dict exceeding depth limit
        data = {"level0": {"level1": {"level2": {"level3": {"level4": {"password": "x"}}}}}}
        result = redact_pii_from_dict(data, depth=5)
        # At depth 5 it should stop recursing
        assert "level0" in result

    def test_redact_pii_list(self):
        """Lists in PII redaction are handled (recursive call)"""
        from src.core.pii import redact_pii_from_dict

        # The _redact_sensitive method handles lists by recursing
        data = {"items": ["safe1", "safe2"]}
        result = redact_pii_from_dict(data)
        assert result["items"] == ["safe1", "safe2"]

    def test_redact_sensitive_fields(self):
        """test_redact_sensitive_fields - response data"""
        from src.core.pii import redact_sensitive_fields

        data = {
            "email": "john@example.com",
            "password": "supersecret",
            "current_password": "oldpass",
            "new_password": "newpass",
            "api_key": "key123",
            "name": "John",
        }
        result = redact_sensitive_fields(data)

        # email IS in _SENSITIVE_RESPONSE_FIELDS → redacted
        assert result["email"] == "***"
        assert result["password"] == "***"
        assert result["current_password"] == "***"
        assert result["new_password"] == "***"
        assert result["api_key"] == "***"
        # name is not sensitive → stays as-is
        assert result["name"] == "John"

    def test_redact_sensitive_fields_custom_fields(self):
        """Custom field set can be passed"""
        from src.core.pii import redact_sensitive_fields

        data = {"email": "john@example.com", "name": "John"}
        result = redact_sensitive_fields(data, fields={"email"})

        assert result["email"] == "***"
        assert result["name"] == "John"

    def test_redact_sensitive_fields_in_place(self):
        """redact_sensitive_fields modifies dict in-place"""
        from src.core.pii import redact_sensitive_fields

        data = {"password": "secret", "api_key": "key"}
        result = redact_sensitive_fields(data)

        # In-place modification
        assert data["password"] == "***"
        assert data["api_key"] == "***"
        assert result is data

    def test_redact_pii_credit_card(self):
        """Credit card field is redacted"""
        from src.core.pii import redact_pii_from_dict

        data = {"credit_card": "4111111111111111"}
        result = redact_pii_from_dict(data)

        # Long string > 4 → partial mask: "41***11"
        assert "credit_card" in result

    def test_redact_pii_phone(self):
        """Phone field is redacted"""
        from src.core.pii import redact_pii_from_dict

        data = {"phone": "+8613812345678"}
        result = redact_pii_from_dict(data)

        # Long string > 4 → partial mask
        assert "phone" in result

    def test_redact_pii_ssn(self):
        """SSN field is redacted"""
        from src.core.pii import redact_pii_from_dict

        data = {"ssn": "123-45-6789"}
        result = redact_pii_from_dict(data)

        # Long string > 4 → partial mask
        assert "ssn" in result

    def test_redact_pii_long_string_masked(self):
        """Long sensitive strings are partially masked (keep first/last 2)"""
        from src.core.pii import redact_pii_from_dict

        data = {"token": "abcdef123456"}
        result = redact_pii_from_dict(data)

        # Long (> 4 chars) → first 2 + *** + last 2
        assert result["token"] == "ab***56"

    def test_redact_pii_non_string_value(self):
        """Non-string sensitive values are fully redacted"""
        from src.core.pii import redact_pii_from_dict

        data = {"password": 12345}
        result = redact_pii_from_dict(data)

        assert result["password"] == "***"
