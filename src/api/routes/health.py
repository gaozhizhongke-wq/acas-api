"""
ACAS v2 - Health Check Routes
Dynamic health checks with dependency validation
"""

import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter
from core.database import db
from core.rate_limit import rate_limiter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check - always returns 200 if process is alive"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness probe - checks all critical dependencies
    Returns 200 only if all dependencies are healthy
    """
    import logging
    logger = logging.getLogger(__name__)
    
    checks = {
        "database": False,
        "redis": False
    }
    
    # Check database
    try:
        checks["database"] = await db.health_check()
        logger.info(f"Database health check: {checks['database']}")
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"] = False
    
    # Check Redis (sync client — use thread pool to avoid blocking)
    try:
        if rate_limiter._redis is not None:
            result = await asyncio.to_thread(rate_limiter._redis.ping)
            checks["redis"] = bool(result)
            logger.info(f"Redis health check: {checks['redis']}")
        else:
            logger.warning("Redis not initialized")
            checks["redis"] = False
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        checks["redis"] = False
    
    all_healthy = all(checks.values())
    
    # Return 503 if not ready
    from fastapi.responses import JSONResponse
    status_code = 200 if all_healthy else 503
    
    response_content = {
        "ready": all_healthy,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    logger.info(f"Readiness check result: {all_healthy}, status_code={status_code}")
    
    return JSONResponse(
        status_code=status_code,
        content=response_content
    )


@router.get("/live")
async def liveness_check():
    """Liveness probe - Kubernetes uses this to restart dead pods"""
    return {
        "alive": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/startup")
async def startup_check():
    """
    Startup probe - for slow-starting containers
    Kubernetes waits for this before accepting traffic
    """
    # Check if app has finished initializing
    # This could check if ML models are loaded, etc.
    return {
        "started": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
