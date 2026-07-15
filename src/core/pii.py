"""
ACAS v2 - PII (Personally Identifiable Information) Protection
Email/phone/name masking and log redaction
"""

import re
from typing import Any, Dict, Optional


# ── Masking patterns ──────────────────────────────────────────

_EMAIL_PATTERN = re.compile(r'([\w.+-]+)@([\w-]+\.\w{2,})')
_PHONE_PATTERN = re.compile(r'(\+?\d{1,3})?[-.\s]?(\d{3,4})[-.\s]?(\d{4})[-.\s]?(\d{4})')

def mask_email(email: str) -> str:
    """Mask email: j***@example.com"""
    def _mask(m):
        name = m.group(1)
        if len(name) <= 2:
            masked_name = name[0] + '***'
        else:
            masked_name = name[0] + '***' + name[-1]
        return f'{masked_name}@{m.group(2)}'
    return _EMAIL_PATTERN.sub(_mask, email)


def mask_name(name: str) -> str:
    """Mask name: Zhang S**"""
    parts = name.strip().split()
    if not parts:
        return name
    if len(parts) >= 2:
        # Keep first and last char of surname, mask given name
        return f'{parts[0][0]}**' + (f' {parts[1][0]}**' if len(parts) > 1 else '')
    return parts[0][0] + '**'


# ── Dict log redaction ────────────────────────────────────────

_PII_KEYS = {'email', 'password', 'token', 'secret', 'api_key', 'access_key',
             'phone', 'mobile', 'credit_card', 'ssn', 'id_card'}


def redact_pii_from_dict(d: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
    """Recursively redact PII fields from a dict (for structlog processors)"""
    if depth > 5:
        return d
    result: Dict[str, Any] = {}
    for key, value in d.items():
        key_lower = str(key).lower()
        if any(pii_key in key_lower for pii_key in _PII_KEYS):
            # Keep type info but mask value
            if isinstance(value, str):
                if '@' in value:
                    result[key] = mask_email(value)
                elif len(value) > 4:
                    result[key] = value[:2] + '***' + value[-2:]
                else:
                    result[key] = '***'
            else:
                result[key] = '***'
        elif isinstance(value, dict):
            result[key] = redact_pii_from_dict(value, depth + 1)
        else:
            result[key] = value
    return result


# ── Response serialization helpers ────────────────────────────

_SENSITIVE_RESPONSE_FIELDS = {'email', 'password', 'current_password',
                              'new_password', 'api_key', 'secret_key'}


def redact_sensitive_fields(data: dict, fields: Optional[set] = None) -> dict:
    """Redact sensitive fields from API response dict (in-place)"""
    target = fields or _SENSITIVE_RESPONSE_FIELDS
    for key in list(data.keys()):
        key_lower = key.lower()
        if key_lower in target:
            data[key] = '***'
    return data
