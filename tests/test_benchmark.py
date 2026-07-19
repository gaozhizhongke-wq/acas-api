"""
ACAS v2 - Performance Benchmarks
Tests for API response times, throughput, and resource usage
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Tuple
import statistics

from httpx import AsyncClient
from src.api.models import User
from sqlalchemy import select


class TestAPIPerformance:
    """API endpoint performance benchmarks"""

    @pytest.mark.asyncio
    async def test_health_endpoint_latency(self, client: AsyncClient):
        """Test /health endpoint latency (should be <50ms)"""
        latencies = []

        for _ in range(20):
            start = time.perf_counter()
            response = await client.get("/health")
            end = time.perf_counter()

            assert response.status_code == 200
            latencies.append((end - start) * 1000)  # Convert to ms

        avg_latency = statistics.mean(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile

        print(f"\n/health latency: avg={avg_latency:.2f}ms, p95={p95_latency:.2f}ms")

        assert avg_latency < 50, f"Average latency too high: {avg_latency:.2f}ms"
        assert p95_latency < 100, f"P95 latency too high: {p95_latency:.2f}ms"

    @pytest.mark.asyncio
    async def test_auth_login_latency(self, client: AsyncClient, test_user_data: dict, test_user):
        """Test /auth/login endpoint latency (should be <200ms)"""
        latencies = []

        for _ in range(10):
            start = time.perf_counter()
            response = await client.post(
                "/auth/login",
                json={
                    "email": test_user_data["email"],
                    "password": test_user_data["password"]
                }
            )
            end = time.perf_counter()

            assert response.status_code == 200
            latencies.append((end - start) * 1000)

        avg_latency = statistics.mean(latencies)
        print(f"\n/auth/login latency: avg={avg_latency:.2f}ms")

        assert avg_latency < 200, f"Login latency too high: {avg_latency:.2f}ms"

    @pytest.mark.asyncio
    async def test_auth_me_throughput(self, client: AsyncClient, auth_headers: dict):
        """Test /auth/me throughput (should handle 50+ req/s)"""
        num_requests = 100
        start = time.perf_counter()

        tasks = []
        for _ in range(num_requests):
            tasks.append(client.get("/auth/me", headers=auth_headers))

        responses = await asyncio.gather(*tasks)
        end = time.perf_counter()

        # Check all succeeded
        for resp in responses:
            assert resp.status_code == 200

        duration = end - start
        throughput = num_requests / duration

        print(f"\n/auth/me throughput: {throughput:.2f} req/s")

        assert throughput > 50, f"Throughput too low: {throughput:.2f} req/s"

    @pytest.mark.asyncio
    async def test_users_list_pagination(self, client: AsyncClient, admin_user, db_session):
        """Test /users/ endpoint with pagination performance"""
        # Login as admin
        login_resp = await client.post(
            "/auth/login",
            json={"email": admin_user.email, "password": "AdminPassword123!"}
        )
        admin_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        # Create test users
        from src.core.security import password_manager
        for i in range(50):
            from src.api.models import User
            user = User(
                email=f"perftest{i}@example.com",
                name=f"Perf Test {i}",
                hashed_password=password_manager.hash("Password123!"),
                role="user"
            )
            db_session.add(user)
        await db_session.commit()

        # Test pagination
        start = time.perf_counter()
        response = await client.get("/users/?limit=10", headers=admin_headers)
        end = time.perf_counter()

        assert response.status_code == 200
        latency = (end - start) * 1000

        print(f"\n/users/ (limit=10) latency: {latency:.2f}ms")
        assert latency < 100, f"User list latency too high: {latency:.2f}ms"


class TestSentimentPerformance:
    """Sentiment analysis performance benchmarks"""

    @pytest.mark.asyncio
    async def test_rule_based_latency(self):
        """Test rule-based sentiment analysis latency (should be <100ms)"""
        from src.sentiment.sentiment_analyzer import RuleBasedSentimentAnalyzer

        analyzer = RuleBasedSentimentAnalyzer()
        await analyzer.initialize()

        test_texts = [
            "The market is experiencing strong growth.",
            "There is a severe shortage and supply chain disruption.",
            "Normal conditions reported in the region.",
        ] * 10  # 30 texts

        latencies = []
        for text in test_texts:
            start = time.perf_counter()
            result = await analyzer.analyze(text)
            end = time.perf_counter()

            assert result.label is not None
            latencies.append((end - start) * 1000)

        avg_latency = statistics.mean(latencies)
        print(f"\nRule-based sentiment latency: avg={avg_latency:.2f}ms")

        assert avg_latency < 100, f"Rule-based latency too high: {avg_latency:.2f}ms"

    @pytest.mark.asyncio
    async def test_rule_based_batch_throughput(self):
        """Test batch sentiment analysis throughput"""
        from src.sentiment.sentiment_analyzer import RuleBasedSentimentAnalyzer

        analyzer = RuleBasedSentimentAnalyzer()
        await analyzer.initialize()

        test_texts = ["Good news for the market!"] * 100

        start = time.perf_counter()
        results = await analyzer.analyze_batch(test_texts)
        end = time.perf_counter()

        assert len(results) == 100
        duration = end - start
        throughput = 100 / duration

        print(f"\nRule-based batch throughput: {throughput:.2f} texts/s")
        assert throughput > 500, f"Batch throughput too low: {throughput:.2f} texts/s"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Transformers model not always available")
    async def test_transformers_latency(self):
        """Test transformers sentiment analysis latency (should be <500ms)"""
        from src.sentiment.sentiment_analyzer import TransformersSentimentAnalyzer

        analyzer = TransformersSentimentAnalyzer()
        success = await analyzer.initialize()

        if not success:
            pytest.skip("Transformers model not available")

        test_text = "The market is experiencing strong growth and positive expansion."

        latencies = []
        for _ in range(10):
            start = time.perf_counter()
            result = await analyzer.analyze(test_text)
            end = time.perf_counter()

            assert result.label is not None
            latencies.append((end - start) * 1000)

        avg_latency = statistics.mean(latencies)
        print(f"\nTransformers sentiment latency: avg={avg_latency:.2f}ms")

        assert avg_latency < 500, f"Transformers latency too high: {avg_latency:.2f}ms"


class TestForecastPerformance:
    """Forecasting engine performance benchmarks"""

    @pytest.mark.asyncio
    async def test_holt_forecast_latency(self):
        """Test Holt's linear method forecast latency (should be <200ms)"""
        from src.ml.timesfm_engine import TimesFMEngine, ForecastModelType
        from datetime import datetime, timedelta

        engine = TimesFMEngine()
        await engine.initialize()

        # Generate test data
        data = [
            (datetime.now() - timedelta(days=i), 100.0 + i * 0.5)
            for i in range(30, 0, -1)
        ]

        latencies = []
        for _ in range(10):
            start = time.perf_counter()
            result = await engine.forecast(
                data,
                forecast_horizon=30,
                model_type=ForecastModelType.HOLT_LINEAR
            )
            end = time.perf_counter()

            assert len(result.values) == 30
            latencies.append((end - start) * 1000)

        avg_latency = statistics.mean(latencies)
        print(f"\nHolt's method forecast latency: avg={avg_latency:.2f}ms")

        assert avg_latency < 200, f"Forecast latency too high: {avg_latency:.2f}ms"

    @pytest.mark.asyncio
    async def test_forecast_scaling(self):
        """Test forecast performance with different data sizes"""
        from src.ml.timesfm_engine import TimesFMEngine, ForecastModelType

        engine = TimesFMEngine()
        await engine.initialize()

        data_sizes = [10, 30, 50, 100]
        results = {}

        for size in data_sizes:
            data = [
                (datetime.now() - timedelta(days=i), 100.0 + i * 0.1)
                for i in range(size, 0, -1)
            ]

            start = time.perf_counter()
            result = await engine.forecast(
                data,
                forecast_horizon=30,
                model_type=ForecastModelType.HOLT_LINEAR
            )
            end = time.perf_counter()

            latency = (end - start) * 1000
            results[size] = latency
            print(f"\nForecast latency with {size} data points: {latency:.2f}ms")

        # Latency should scale reasonably (not exponentially)
        # Holt-Linear has O(n) per iteration; allow scaling factor
        assert results[100] < max(results[10] * 70, 200.0), "Forecast latency scaling poorly"

    @pytest.mark.asyncio
    async def test_batch_forecast_throughput(self):
        """Test batch forecasting throughput"""
        from src.ml.timesfm_engine import TimesFMEngine, ForecastModelType

        engine = TimesFMEngine()
        await engine.initialize()

        # Prepare 10 product series
        product_series = {}
        for i in range(10):
            product_series[f"product_{i}"] = [
                (datetime.now() - timedelta(days=j), 100.0 + j * 0.1)
                for j in range(30, 0, -1)
            ]

        start = time.perf_counter()
        results = await engine.batch_forecast(
            product_series,
            forecast_horizon=30,
            model_type=ForecastModelType.HOLT_LINEAR
        )
        end = time.perf_counter()

        assert len(results) == 10
        duration = end - start
        throughput = 10 / duration

        print(f"\nBatch forecast throughput: {throughput:.2f} products/s")
        assert throughput > 5, f"Batch forecast throughput too low: {throughput:.2f} products/s"


class TestDatabasePerformance:
    """Database query performance benchmarks"""

    @pytest.mark.asyncio
    async def test_user_query_latency(self, db_session, test_user):
        """Test user query latency (should be <10ms)"""
        from sqlalchemy import select, text

        latencies = []

        for _ in range(20):
            start = time.perf_counter()
            result = await db_session.execute(
                select(User).where(User.id == test_user.id)
            )
            user = result.scalar_one_or_none()
            end = time.perf_counter()

            assert user is not None
            latencies.append((end - start) * 1000)

        avg_latency = statistics.mean(latencies)
        print(f"\nUser query latency: avg={avg_latency:.2f}ms")

        assert avg_latency < 10, f"User query latency too high: {avg_latency:.2f}ms"

    @pytest.mark.asyncio
    async def test_concurrent_db_queries(self, db_session, test_user):
        """Test concurrent database query performance"""
        from sqlalchemy import select
        import asyncio

        async def query_user():
            result = await db_session.execute(
                select(User).where(User.id == test_user.id)
            )
            return result.scalar_one_or_none()

        # 50 concurrent queries
        start = time.perf_counter()
        tasks = [query_user() for _ in range(50)]
        results = await asyncio.gather(*tasks)
        end = time.perf_counter()

        # All should succeed
        for user in results:
            assert user is not None

        duration = end - start
        qps = 50 / duration

        print(f"\nConcurrent DB queries: {qps:.2f} qps")
        assert qps > 100, f"DB query throughput too low: {qps:.2f} qps"


class TestMemoryUsage:
    """Memory usage benchmarks"""

    @pytest.mark.asyncio
    async def test_api_memory_usage(self, client: AsyncClient, auth_headers: dict):
        """Test API memory usage doesn't grow unboundedly"""
        try:
            import psutil
            process = psutil.Process()
        except ImportError:
            pytest.skip("psutil not installed")

        # Baseline memory
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Make 1000 requests
        for _ in range(1000):
            response = await client.get("/auth/me", headers=auth_headers)
            assert response.status_code == 200

        # Check memory after requests
        current_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = current_memory - baseline_memory

        print(f"\nMemory usage: baseline={baseline_memory:.2f}MB, current={current_memory:.2f}MB, increase={memory_increase:.2f}MB")

        # Memory increase should be minimal (<50MB)
        assert memory_increase < 50, f"Memory leak detected: {memory_increase:.2f}MB increase"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
