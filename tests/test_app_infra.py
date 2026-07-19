"""
Coverage for src.api.main production infrastructure:
- Application lifespan (startup/shutdown: DB, rate limiter, token manager, ML init)
- ML graceful degradation (timeout / exception paths)
- Security headers & request middleware
- Rate-limit middleware (disabled path, 429 path)
- Exception handlers (AuthenticationError -> 401, generic Exception -> 500)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from httpx import AsyncClient, ASGITransport

from src.api.main import app, lifespan
from src.core.security import AuthenticationError


def _make_ml_engine(initialized=False):
    eng = MagicMock()
    eng._initialized = initialized
    eng._models = {}
    eng._arima_available = False
    eng.initialize = AsyncMock(return_value=initialized)
    eng.close = AsyncMock()
    return eng


@pytest.mark.asyncio
async def test_lifespan_startup_and_shutdown():
    """Cover lifespan startup (DB/rate-limiter/token-manager/ML init) and shutdown."""
    mock_db = MagicMock()
    mock_db.initialize = AsyncMock()
    mock_db.create_tables = AsyncMock()
    mock_db.close = AsyncMock()
    mock_rl = MagicMock()
    mock_rl._redis = MagicMock()
    mock_rl.connect = AsyncMock()
    mock_rl.close = AsyncMock()
    mock_tm = MagicMock()
    mock_tm.initialize = AsyncMock()

    ts_engine = _make_ml_engine(False)
    sp_engine = _make_ml_engine(False)
    ie_engine = MagicMock()
    ie_engine._analyzer = MagicMock(_initialized=False, _use_transformers=False)
    ie_engine.initialize = AsyncMock()
    ie_engine.close = AsyncMock()

    with patch("src.api.main.db", mock_db), \
         patch("src.api.main.rate_limiter", mock_rl), \
         patch("src.api.main.token_manager", mock_tm), \
         patch("src.ml.timesfm_engine.timesfm_engine", ts_engine), \
         patch("src.ml.sales_predictor.sales_predictor", sp_engine), \
         patch("src.sentiment.intelligence_engine.intelligence_engine", ie_engine):
        async with lifespan(app):
            pass

    mock_db.initialize.assert_awaited()
    mock_db.create_tables.assert_awaited()
    mock_rl.connect.assert_awaited()
    mock_tm.initialize.assert_awaited()
    ts_engine.initialize.assert_awaited()
    sp_engine.initialize.assert_awaited()
    ie_engine.initialize.assert_awaited()
    # shutdown
    ie_engine.close.assert_awaited()
    mock_rl.close.assert_awaited()
    mock_db.close.assert_awaited()


@pytest.mark.asyncio
async def test_lifespan_ml_timeout_degradation():
    """Cover the asyncio.TimeoutError branches in _init_ml_safely."""
    mock_db = MagicMock()
    mock_db.initialize = AsyncMock()
    mock_db.create_tables = AsyncMock()
    mock_db.close = AsyncMock()
    mock_rl = MagicMock()
    mock_rl._redis = MagicMock()
    mock_rl.connect = AsyncMock()
    mock_rl.close = AsyncMock()
    mock_tm = MagicMock()
    mock_tm.initialize = AsyncMock()

    async def _hang(*a, **k):
        await asyncio.sleep(60)

    ts_engine = _make_ml_engine(False)
    ts_engine.initialize = AsyncMock(side_effect=asyncio.TimeoutError())
    sp_engine = _make_ml_engine(False)
    sp_engine.initialize = AsyncMock(side_effect=asyncio.TimeoutError())
    ie_engine = MagicMock()
    ie_engine._analyzer = MagicMock(_initialized=False, _use_transformers=False)
    ie_engine.initialize = AsyncMock(side_effect=asyncio.TimeoutError())
    ie_engine.close = AsyncMock()

    with patch("src.api.main.db", mock_db), \
         patch("src.api.main.rate_limiter", mock_rl), \
         patch("src.api.main.token_manager", mock_tm), \
         patch("src.ml.timesfm_engine.timesfm_engine", ts_engine), \
         patch("src.ml.sales_predictor.sales_predictor", sp_engine), \
         patch("src.sentiment.intelligence_engine.intelligence_engine", ie_engine):
        async with lifespan(app):
            pass  # must still start despite ML timeouts

    ie_engine.close.assert_awaited()


@pytest.mark.asyncio
async def test_lifespan_ml_exception_degradation():
    """Cover the generic Exception branches in _init_ml_safely."""
    mock_db = MagicMock()
    mock_db.initialize = AsyncMock()
    mock_db.create_tables = AsyncMock()
    mock_db.close = AsyncMock()
    mock_rl = MagicMock()
    mock_rl._redis = MagicMock()
    mock_rl.connect = AsyncMock()
    mock_rl.close = AsyncMock()
    mock_tm = MagicMock()
    mock_tm.initialize = AsyncMock()

    ts_engine = _make_ml_engine(False)
    ts_engine.initialize = AsyncMock(side_effect=RuntimeError("boom"))
    sp_engine = _make_ml_engine(False)
    sp_engine.initialize = AsyncMock(side_effect=RuntimeError("boom"))
    ie_engine = MagicMock()
    ie_engine._analyzer = MagicMock(_initialized=False, _use_transformers=False)
    ie_engine.initialize = AsyncMock(side_effect=RuntimeError("boom"))
    ie_engine.close = AsyncMock()

    with patch("src.api.main.db", mock_db), \
         patch("src.api.main.rate_limiter", mock_rl), \
         patch("src.api.main.token_manager", mock_tm), \
         patch("src.ml.timesfm_engine.timesfm_engine", ts_engine), \
         patch("src.ml.sales_predictor.sales_predictor", sp_engine), \
         patch("src.sentiment.intelligence_engine.intelligence_engine", ie_engine):
        async with lifespan(app):
            pass

    ie_engine.close.assert_awaited()


@pytest.mark.asyncio
async def test_middleware_security_headers_present(client: AsyncClient):
    """security_headers_middleware adds hardening headers on every response."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "max-age=31536000" in resp.headers.get("Strict-Transport-Security", "")
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_rate_limit_disabled_middleware(client: AsyncClient):
    """Cover rate_limit_middleware early-return when rate limiting is disabled."""
    from src.core import config
    with patch.object(config.rate_limit, "enabled", False):
        resp = await client.get("/health")
        assert resp.status_code == 200


def _add_throwing_route(path: str, exc):
    async def _ep(req: Request):
        raise exc
    app.add_api_route(path, _ep, methods=["GET"])


@pytest.mark.asyncio
async def test_auth_exception_handler_returns_401():
    """AuthenticationError raised in a route -> 401 with WWW-Authenticate header."""
    path = "/__test_auth_err"
    _add_throwing_route(path, AuthenticationError("bad token"))
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(path)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert resp.headers.get("WWW-Authenticate") == "Bearer"
        assert "Authentication failed" in resp.json()["error"]
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != path]


@pytest.mark.asyncio
async def test_generic_exception_handler_returns_500():
    """Unhandled Exception -> 500 (no detail leak when debug is off)."""
    from src.api.main import general_exception_handler
    from unittest.mock import MagicMock

    import json
    req = MagicMock(spec=Request)
    resp = await general_exception_handler(req, RuntimeError("kaboom"))
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    body = json.loads(resp.body)
    assert body["error"] == "Internal server error"


@pytest.mark.asyncio
async def test_http_exception_handler_propagates_status():
    """HTTPException raised in a route is rendered with its status code."""
    path = "/__test_404"
    _add_throwing_route(path, HTTPException(status_code=418, detail="teapot"))
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(path)
        assert resp.status_code == 418
        assert resp.json()["detail"] == "teapot"
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != path]


@pytest.mark.asyncio
async def test_rate_limit_429_response(client: AsyncClient):
    """Cover rate_limit_middleware 429 branch by forcing check() to deny."""
    from src.core.rate_limit import rate_limiter

    class _Deny:
        allowed = False
        retry_after = 1
        remaining = 0
        reset_time = 123

    with patch.object(rate_limiter, "check", AsyncMock(return_value=_Deny())):
        resp = await client.get("/forecast")
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert resp.headers.get("Retry-After") == "1"
