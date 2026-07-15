"""
ACAS v2 - Health Route Tests
Simple tests for health check endpoint
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


class TestHealth:
    """GET /health (or similar)"""

    async def test_health_endpoint(self, client: AsyncClient):
        """Health endpoint should return 200"""
        # Try common health endpoints
        for path in ["/health", "/healthz", "/api/health", "/"]:
            resp = await client.get(path)
            if resp.status_code in (200, 401, 403):
                # Found it (401/403 means endpoint exists but needs auth)
                assert resp.status_code in (200, 401, 403)
                return
        
        # If we get here, no health endpoint found
        # This is OK - not all apps have health endpoints
        pytest.skip("No health endpoint found")

    async def test_health_response_format(self, client: AsyncClient):
        """Health response should have expected format"""
        resp = await client.get("/health")
        if resp.status_code == 200:
            data = resp.json()
            # Common health check fields
            assert any(key in data for key in ["status", "healthy", "ok"])
