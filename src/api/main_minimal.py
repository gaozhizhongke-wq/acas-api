"""
Minimal ACAS v2 Application for Load Testing
Bypasses all ML modules for fast startup
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="ACAS v2 - Minimal (Load Testing)",
    description="Minimal version for load testing without ML",
    version="2.0.0-minimal"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "version": "2.0.0-minimal",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/ready")
async def readiness_check():
    """Readiness probe"""
    return JSONResponse(
        status_code=200,
        content={
            "ready": True,
            "checks": {
                "database": True,
                "redis": True
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )

@app.get("/live")
async def liveness_check():
    """Liveness probe"""
    return {
        "alive": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/startup")
async def startup_check():
    """Startup probe"""
    return {
        "started": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics (minimal)"""
    return """
# HELP acas_http_requests_total Total HTTP requests
# TYPE acas_http_requests_total counter
acas_http_requests_total{method="GET",endpoint="/health",status="200"} 1

# HELP acas_http_request_duration_seconds HTTP request duration
# TYPE acas_http_request_duration_seconds histogram
acas_http_request_duration_seconds_bucket{le="0.1"} 1
acas_http_request_duration_seconds_bucket{le="0.5"} 1
acas_http_request_duration_seconds_bucket{le="1.0"} 1
acas_http_request_duration_seconds_bucket{le="+Inf"} 1
"""

# Auth endpoints (mock)
@app.post("/api/auth/register")
async def register(email: str = "test@example.com", password: str = "password", name: str = "Test"):
    """Mock registration"""
    return {
        "id": 1,
        "email": email,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

@app.post("/api/auth/login")
async def login():
    """Mock login"""
    return {
        "access_token": "mock_token_for_load_testing",
        "refresh_token": "mock_refresh_token",
        "token_type": "bearer"
    }

@app.get("/api/users/me")
async def get_current_user():
    """Mock user info"""
    return {
        "id": 1,
        "email": "test@example.com",
        "name": "Test User",
        "role": "user"
    }

@app.post("/api/sentiment/analyze")
async def analyze_sentiment(text: str = "Test text"):
    """Mock sentiment analysis"""
    import random
    return {
        "sentiment": random.choice(["positive", "negative", "neutral"]),
        "confidence": random.uniform(0.7, 0.99),
        "text": text
    }

@app.post("/api/forecast/predict")
async def predict():
    """Mock prediction"""
    return {
        "forecast": [100.0, 105.0, 110.0, 115.0, 120.0],
        "model": "mock"
    }

@app.on_event("startup")
async def startup_event():
    logger.info("Minimal ACAS v2 started (Load Testing Mode)")
    # Pre-warm: hit each endpoint once to initialize FastAPI/Ayncio internals
    import asyncio
    from fastapi.testclient import TestClient
    # warmup is informational only; actual pre-warming is done by load test clients

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Minimal ACAS v2 shutting down")

# Connection pool settings for high concurrency
# Default uvicorn runs single-worker on Windows; set workers=4 for distributed load
if __name__ == "__main__":
    import uvicorn
    # Single-process mode for quick start
    uvicorn.run(app, host="0.0.0.0", port=8000, loop="asyncio", limit_concurrency=1000, backlog=2048)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
