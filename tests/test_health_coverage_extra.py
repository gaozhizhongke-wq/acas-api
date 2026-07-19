"""
Extra health route coverage: success paths for /ready (db + redis healthy),
exception paths for db check, and redis-not-initialized path.
NOTE: route module is 'src.api.routes.health' (not 'src.src.api.routes.health') due to
the dual-module import issue (conftest adds both project root and src/ to path).
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock, AsyncMock


class TestReadinessSuccessPath:
    @pytest.mark.asyncio
    async def test_ready_all_healthy(self, client: AsyncClient):
        """Cover lines 43-44 (db success) and 50-52 (redis success)."""
        with patch("src.api.routes.health.db") as mock_db:
            mock_db.health_check = AsyncMock(return_value=True)
            with patch("src.api.routes.health.rate_limiter") as mock_rl:
                mock_rl._redis = MagicMock()
                mock_rl._redis.ping.return_value = True
                resp = await client.get("/ready")
                assert resp.status_code == 200
                data = resp.json()
                assert data["ready"] is True
                assert data["checks"]["database"] is True
                assert data["checks"]["redis"] is True

    @pytest.mark.asyncio
    async def test_ready_db_exception(self, client: AsyncClient):
        """Cover line 45 (db health_check throws to False)."""
        with patch("src.api.routes.health.db") as mock_db:
            mock_db.health_check = AsyncMock(side_effect=RuntimeError("db down"))
            with patch("src.api.routes.health.rate_limiter") as mock_rl:
                mock_rl._redis = MagicMock()
                mock_rl._redis.ping.return_value = True
                resp = await client.get("/ready")
                assert resp.status_code == 503
                data = resp.json()
                assert data["checks"]["database"] is False

    @pytest.mark.asyncio
    async def test_ready_redis_not_initialized(self, client: AsyncClient):
        """Cover lines 56-57 (redis None to False)."""
        with patch("src.api.routes.health.db") as mock_db:
            mock_db.health_check = AsyncMock(return_value=True)
            with patch("src.api.routes.health.rate_limiter") as mock_rl:
                mock_rl._redis = None
                resp = await client.get("/ready")
                assert resp.status_code == 503
                data = resp.json()
                assert data["checks"]["redis"] is False

    @pytest.mark.asyncio
    async def test_ready_redis_exception(self, client: AsyncClient):
        """Cover line 58 (redis ping throws to False)."""
        with patch("src.api.routes.health.db") as mock_db:
            mock_db.health_check = AsyncMock(return_value=True)
            with patch("src.api.routes.health.rate_limiter") as mock_rl:
                mock_rl._redis = MagicMock()
                mock_rl._redis.ping.side_effect = Exception("redis down")
                resp = await client.get("/ready")
                assert resp.status_code == 503
                data = resp.json()
                assert data["checks"]["redis"] is False
