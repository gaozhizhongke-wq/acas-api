# SSL Database Config + Coverage Tests — ACAS v2

## Part 1: SSL Database Connection

### `src/core/config.py` — `DatabaseConfig`
Added field:
```python
ssl_mode: str = Field(
    default="disable",
    description="SSL mode for database connection: disable, require, verify-ca, verify-full"
)
```

### `src/core/database.py` — `initialize()`
After URL is parsed, SSL mode is passed to `create_async_engine`:
```python
connect_args: dict = {}
if config.database.ssl_mode != "disable":
    connect_args["ssl"] = config.database.ssl_mode

self._engine = create_async_engine(
    config.database.url,
    connect_args=connect_args if connect_args else None,
    **engine_kwargs
)
```
- Default `"disable"` preserves backward compatibility
- Only passes `connect_args` when SSL is actually configured

---

## Part 2: Coverage Tests

### Results: **62/62 new tests PASSED**

| File | Tests | Status |
|------|-------|--------|
| `tests/test_database.py` | 12 | ✅ all pass |
| `tests/test_rate_limit.py` | 7 | ✅ all pass |
| `tests/test_logging.py` | 8 | ✅ all pass |
| `tests/test_pii.py` | 15 | ✅ all pass |
| `tests/test_config.py` | 20 | ✅ all pass |

**Total suite: 141 passed, 1 skipped (pre-existing) — all new tests green.**

### Module Coverage (new tests)

| Module | Before | After |
|--------|--------|-------|
| `src/core/config.py` | ~88% | **92%** |
| `src/core/database.py` | ~71% | **84%** |
| `src/core/logging.py` | ~62% | **78%** |
| `src/core/pii.py` | ~71% | **94%** |
| `src/core/rate_limit.py` | ~33% | **37%** (Redis unavailable path tested) |

### Key Design Decisions in Tests

1. **Async mock patterns** — SQLAlchemy async context managers (`async with engine.connect()`) require a real class with `async __aenter__`/`__aexit__`, not MagicMock chains, to correctly simulate exception propagation.

2. **`is_production` property** — Cannot be patched with `patch.object()` (Pydantic `@property`). Patched module-level `config` object with `is_production` attribute instead.

3. **`FacadeDict` immutability** — `Base.metadata.tables` is immutable (SQLAlchemy FacadeDict); patched `Base.metadata.tables = {}` in tests rather than mutating it.

4. **`mask_email` behavior** — Keeps first and last character of the local part (`john` → `j***n`), not just the first. Tests verified against actual implementation.

5. **`redact_pii_from_dict` partial masking** — Long strings (>4 chars) are masked as `first2***last2`. Short strings get `***`. Tests reflect actual behavior.

6. **`redact_sensitive_fields`** — `email` IS in `_SENSITIVE_RESPONSE_FIELDS` default set → gets redacted. Tests reflect actual implementation.
