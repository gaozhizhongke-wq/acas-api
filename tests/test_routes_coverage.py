"""
Route-layer coverage tests for sentiment and intelligence endpoints.
These exercise routes that were previously untested (return statements uncovered).
ML is disabled in conftest, so rule-based fallback is used.
Uses conftest's client + auth_headers fixtures (which patch both DB instances).
"""

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def _dummy():
    yield None


class TestSentimentRoutes:
    @pytest.mark.asyncio
    async def test_analyze_sentiment(self, client, auth_headers):
        resp = await client.post(
            "/sentiment/analyze",
            json={"text": "Prices are surging, severe shortage reported."},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "label" in data
        assert "score" in data
        assert "model" in data

    @pytest.mark.asyncio
    async def test_analyze_batch(self, client, auth_headers):
        resp = await client.post(
            "/sentiment/batch",
            json={"texts": ["Great growth!", "Terrible crisis.", "Normal conditions."]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["results"]) == 3

    @pytest.mark.asyncio
    async def test_analyze_aspects(self, client, auth_headers):
        resp = await client.post(
            "/sentiment/aspects",
            json={"text": "Severe shortage reported. Logistics delays expected."},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "overall" in data
        assert "risk_indicators" in data
        assert "summary" in data

    @pytest.mark.asyncio
    async def test_analyze_requires_auth(self, client):
        resp = await client.post(
            "/sentiment/analyze",
            json={"text": "test"},
        )
        assert resp.status_code in (401, 403)


class TestIntelligenceRoutes:
    @pytest.mark.asyncio
    async def test_get_market_intelligence(self, client, auth_headers):
        resp = await client.get(
            "/intelligence/market",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_sentiment" in data
        assert "risk_alerts" in data
        assert "news_volume" in data

    @pytest.mark.asyncio
    async def test_get_alerts(self, client, auth_headers):
        resp = await client.get(
            "/intelligence/alerts",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_alert_detail_not_found(self, client, auth_headers):
        resp = await client.get(
            "/intelligence/alerts/nonexistent-id",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_start_monitoring(self, client, auth_headers):
        resp = await client.post(
            "/intelligence/monitor/start?interval_minutes=5",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "monitoring_started"

    @pytest.mark.asyncio
    async def test_stop_monitoring(self, client, auth_headers):
        resp = await client.post(
            "/intelligence/monitor/stop",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "monitoring_stopped"

    @pytest.mark.asyncio
    async def test_market_requires_auth(self, client):
        resp = await client.get("/intelligence/market")
        assert resp.status_code in (401, 403)
