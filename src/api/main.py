"""
ACAS v2 - FastAPI Application
Enterprise-grade API with auth, rate limiting, observability, security headers
"""

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

# Windows ProactorEventLoop compatibility fix for psycopg3
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from src.core.config import config
from src.core.database import db
from src.core.logging import setup_logging, get_logger, LoggerAdapter
from src.core.metrics import metrics_tracker
from src.core.rate_limit import rate_limiter, RateLimitResult
from src.core.security import AuthenticationError, token_manager

from src.api.routes import auth, users, forecast, intelligence, sentiment, health

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    setup_logging()

    # Initialize Sentry if DSN configured
    sentry_dsn = getattr(config, 'sentry_dsn', None) or os.getenv('ACAS_SENTRY_DSN')
    if sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=config.environment,
                traces_sample_rate=0.1 if not config.is_production else 0.05,
                profiles_sample_rate=0.05,
                release=f"acas@{config.app_version}",
            )
            logger.info("Sentry initialized", extra={"dsn": sentry_dsn[:40] + "..."})
        except Exception as e:
            logger.warning(f"Sentry initialization failed: {e}")
    else:
        logger.warning("Sentry DSN not configured — error tracking disabled")

    logger.info(f"ACAS v{config.app_version} starting up", extra={
        "environment": config.environment
    })

    # Initialize database
    await db.initialize()

    # Auto-create tables if needed (non-production)
    if not config.is_production:
        try:
            await db.create_tables()
            logger.info("Database tables verified/created")
        except Exception as e:
            logger.warning(f"create_tables failed ({e}), attempting force recreate")
            try:
                await db.create_tables(force=True)
                logger.info("Database tables force recreated")
            except Exception as e2:
                logger.error(f"Failed to create database tables: {e2}")
                raise

    # Initialize rate limiter
    await rate_limiter.connect()

    # Initialize token manager with Redis for blacklist
    await token_manager.initialize(rate_limiter._redis if rate_limiter._redis else None)

    # Initialize ML models (with graceful failure — app must start even if ML fails)
    import asyncio
    from src.ml.timesfm_engine import timesfm_engine
    from src.ml.sales_predictor import sales_predictor
    from src.sentiment.intelligence_engine import intelligence_engine

    async def _init_ml_safely():
        """Initialize ML with timeout and graceful error handling."""

        try:
            timesfm_ok = await asyncio.wait_for(timesfm_engine.initialize(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("TimesFM initialization timed out (30s) — continuing without it")
            timesfm_ok = False
        except Exception as e:
            logger.warning(f"TimesFM initialization failed: {e}")
            timesfm_ok = False

        try:
            predictor_ok = await asyncio.wait_for(sales_predictor.initialize(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Sales predictor initialization timed out (30s) — continuing without it")
            predictor_ok = False
        except Exception as e:
            logger.warning(f"Sales predictor initialization failed: {e}")
            predictor_ok = False

        try:
            # intelligence_engine.initialize() itself guards disabled sub-components
            await asyncio.wait_for(intelligence_engine.initialize(), timeout=60)
        except asyncio.TimeoutError:
            logger.warning("Intelligence engine initialization timed out (60s) — continuing without it")
        except Exception as e:
            logger.warning(f"Intelligence engine initialization failed: {e}")

        # Honest ML status report — reflects actual initialized state
        available_models = []
        if timesfm_engine._initialized:
            models_in_engine = list(timesfm_engine._models.keys())
            model_names = [m.value for m in models_in_engine]
            if getattr(timesfm_engine, '_arima_available', False):
                model_names.append('arima')
            available_models = model_names

        ml_status = {
            "forecast_engine": "ready" if timesfm_engine._initialized else "unavailable",
            "available_models": available_models,
            "sales_predictor": "ready" if sales_predictor._initialized else "unavailable",
            "sentiment_mode": ("transformers" if getattr(intelligence_engine._analyzer, '_use_transformers', False)
                               else "rule-based" if intelligence_engine._analyzer._initialized
                               else "unavailable"),
        }
        logger.info(f"ML services status: {ml_status}")

    # Run ML initialization with timeout — app starts even if ML fails
    await _init_ml_safely()

    yield

    # Shutdown
    logger.info("Shutting down...")
    await intelligence_engine.close()
    await rate_limiter.close()
    await db.close()


# Create app
app = FastAPI(
    title="ACAS API",
    description="Africa Commodity Analytics System - Enterprise Edition",
    version=config.app_version,
    lifespan=lifespan,
    docs_url="/docs" if not config.is_production else None,
    redoc_url="/redoc" if not config.is_production else None,
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api.cors_origins_list,
    allow_credentials=config.api.cors_allow_credentials,
    allow_methods=config.api.cors_allow_methods.split(","),
    allow_headers=config.api.cors_allow_headers.split(","),
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # Remove server header for security
    if "server" in response.headers:
        del response.headers["server"]

    return response


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Request logging, correlation ID, and metrics tracking"""
    start_time = time.time()

    # Increment active requests gauge
    metrics_tracker.inc_active()

    # Generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID", str(time.time())[:8])
    request.state.correlation_id = correlation_id

    # Create logger adapter
    request_logger = LoggerAdapter(
        logger,
        correlation_id=correlation_id,
        request_id=request.headers.get("X-Request-ID"),
        user_id=getattr(request.state, "user_id", None)
    )

    request.state.logger = request_logger

    # Log request (without sensitive paths)
    path = request.url.path
    if not any(s in path for s in ["/health", "/ready", "/live", "/metrics"]):
        request_logger.info(
            f"{request.method} {path}",
            extra={"extra": {"client": request.client.host if request.client else None}}
        )

    # Process request
    try:
        response = await call_next(request)
    except Exception as e:
        request_logger.error("Request failed", exc_info=e)
        raise
    finally:
        # Always decrement active gauge and record metrics
        metrics_tracker.dec_active()

    # Record request duration, endpoint (generalized), and status code
    duration = time.time() - start_time
    metrics_tracker.record_request(
        method=request.method,
        raw_path=path,
        status_code=response.status_code,
        duration=duration,
    )

    # Log response
    if not any(s in path for s in ["/health", "/ready", "/live", "/metrics"]):
        request_logger.info(
            f"Response {response.status_code} in {duration:.3f}s",
            extra={"extra": {"duration_ms": int(duration * 1000)}}
        )

    # Add correlation ID to response
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Response-Time"] = f"{duration:.3f}s"

    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware"""
    if not config.rate_limit.enabled:
        return await call_next(request)

    # Skip rate limiting for health checks
    if request.url.path in ["/health", "/ready", "/live", "/metrics"]:
        return await call_next(request)

    # Determine rate limit type
    limit_type = "default"
    if "/auth/login" in request.url.path:
        limit_type = "login"
    elif "/auth/register" in request.url.path:
        limit_type = "register_limit"

    # Build rate limit key
    client_ip = request.client.host if request.client else "unknown"
    key = f"rl:{limit_type}:{client_ip}"

    # Check rate limit
    result = await rate_limiter.check(key, limit_type)

    if not result.allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Rate limit exceeded",
                "retry_after": result.retry_after
            },
            headers={
                "X-RateLimit-Limit": str(result.remaining + 1),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(result.reset_time),
                "Retry-After": str(result.retry_after)
            }
        )

    # Process request
    response = await call_next(request)

    # Add rate limit headers
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(result.reset_time)

    return response


# Exception handlers
@app.exception_handler(AuthenticationError)
async def auth_exception_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "Authentication failed", "detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", exc_info=exc)
    detail = str(exc) if config.debug else None
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error"} | ({"detail": detail} if detail else {})
    )


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(forecast.router, prefix="/forecast", tags=["Forecasting"])
app.include_router(intelligence.router, prefix="/intelligence", tags=["Intelligence"])
app.include_router(sentiment.router, prefix="/sentiment", tags=["Sentiment Analysis"])



@app.get("/")
async def root():
    """API root"""
    return {
        "name": "ACAS API",
        "version": config.app_version,
        "environment": config.environment,
        "status": "operational"
    }


# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    Renders the in-memory MetricsTracker plus app-level gauges in
    Prometheus text exposition format.
    """
    from fastapi.responses import PlainTextResponse

    db_ok = await db.health_check()
    redis_ok = rate_limiter._redis is not None

    content = metrics_tracker.render(
        version=config.app_version,
        environment=config.environment,
        db_ok=db_ok,
        redis_ok=redis_ok,
    )

    return PlainTextResponse(content=content, media_type="text/plain; charset=utf-8")


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.reload,
        workers=config.api.workers if not config.api.reload else 1
    )
