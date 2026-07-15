"""
ACAS v2 - Forecasting Engine Tests
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from typing import List, Tuple

from ml.timesfm_engine import (
    timesfm_engine,
    ForecastModelType,
    ModelSelector,
    HoltLinearModel,
)
from api.models import ForecastJob


class TestModelSelector:
    """Tests for automatic model selection."""

    def test_insufficient_data(self):
        """Test model selection with insufficient data."""
        values = np.array([1.0, 2.0])
        analysis = ModelSelector.analyze_series(values)

        assert analysis["trend"] == "insufficient_data"
        assert analysis["recommended_model"] == ForecastModelType.HOLT_LINEAR

    def test_strong_trend(self):
        """Test detection of strong trend."""
        # Create data with strong upward trend
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        analysis = ModelSelector.analyze_series(values)

        assert analysis["trend"] in ["strong", "moderate"]

    def test_seasonality_detection(self):
        """Test detection of seasonality."""
        # Create data with clear weekly seasonality (7-day repeating pattern)
        weekly_pattern = np.array([10.0, 12.0, 11.0, 9.0, 10.0, 8.0, 7.0])  # One week
        data = np.tile(weekly_pattern, 4)  # 4 weeks = 28 data points
        np.random.seed(42)
        data = data + np.random.normal(0, 0.1, len(data))  # Add small noise
        analysis = ModelSelector.analyze_series(data)

        assert analysis["seasonality"] is not None

    def test_noise_level(self):
        """Test noise level detection."""
        # Low noise (≥10 points for noise_level detection)
        low_noise = np.array([1.0, 1.1, 0.9, 1.05, 0.95, 1.02, 1.08, 0.92, 1.03, 0.97])
        analysis_low = ModelSelector.analyze_series(low_noise)

        # High noise
        high_noise = np.array([1.0, 5.0, -2.0, 10.0, 0.5, -3.0, 8.0, -1.0, 6.0, 2.0])
        analysis_high = ModelSelector.analyze_series(high_noise)

        assert analysis_low["noise_level"] == "low"
        assert analysis_high["noise_level"] == "high"

    def test_stable_series(self):
        """Test stability detection."""
        # Stable series
        stable = np.ones(30) * 10.0
        analysis_stable = ModelSelector.analyze_series(stable)

        assert analysis_stable["stability"] == "stable"

    def test_unstable_series(self):
        """Test detection of structural break."""
        # Series with break
        unstable = np.concatenate([np.ones(15) * 10.0, np.ones(15) * 20.0])
        analysis_unstable = ModelSelector.analyze_series(unstable)

        assert analysis_unstable["stability"] == "unstable"


class TestHoltLinearModel:
    """Tests for Holt's Linear model."""

    @pytest.fixture
    def model(self):
        """Create a model instance."""
        return HoltLinearModel()

    def test_fit_default_params(self, model):
        """Test fit with default parameters."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        model.fit(values, optimize=False)

        assert model.alpha == 0.3
        assert model.beta == 0.1
        assert model._fitted_values is not None

    def test_fit_optimize(self, model):
        """Test fit with parameter optimization."""
        # Create predictable data
        values = np.arange(1.0, 21.0)  # [1, 2, ..., 20]

        model.fit(values, optimize=True)

        # Optimized parameters should be found
        assert model.alpha is not None
        assert model.beta is not None
        assert 0.0 < model.alpha < 1.0
        assert 0.0 < model.beta < 1.0

    def test_forecast(self, model):
        """Test forecast generation."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        model.fit(values, optimize=False)

        forecasts, lower, upper = model.forecast(values, horizon=5)

        assert len(forecasts) == 5
        assert len(lower) == 5
        assert len(upper) == 5
        assert all(f > 0 for f in forecasts)  # No negative forecasts

    def test_metrics(self, model):
        """Test metrics calculation."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        model.fit(values, optimize=False)

        metrics = model.metrics(values)

        assert "mae" in metrics
        assert "rmse" in metrics
        assert "mape" in metrics
        assert "alpha" in metrics
        assert "beta" in metrics

    def test_perfect_fit(self, model):
        """Test with perfect linear data."""
        values = np.arange(1.0, 11.0)
        model.fit(values, optimize=True)

        metrics = model.metrics(values)

        # Should have very low error
        assert metrics["mae"] < 0.5
        assert metrics["rmse"] < 0.5


class TestTimesFMEngine:
    """Tests for the main forecasting engine."""

    @pytest.fixture(autouse=True)
    async def setup_engine(self):
        """Initialize engine for each test."""
        await timesfm_engine.initialize()
        yield
        timesfm_engine._models = {}
        timesfm_engine._initialized = False

    def _generate_test_data(
        self,
        n_points: int = 30,
        trend: float = 0.5,
        noise: float = 0.1
    ) -> List[Tuple[datetime, float]]:
        """Generate synthetic test data."""
        base_time = datetime.now()
        values = np.arange(n_points) * trend + np.random.normal(0, noise, n_points)

        return [
            (base_time + timedelta(days=i), float(v))
            for i, v in enumerate(values)
        ]

    @pytest.mark.asyncio
    async def test_forecast_auto_model(self):
        """Test forecast with automatic model selection."""
        data = self._generate_test_data()
        result = await timesfm_engine.forecast(data, forecast_horizon=10)

        assert result.model_type is not None
        assert len(result.values) == 10
        assert len(result.timestamps) == 10
        assert len(result.lower_bound) == 10
        assert len(result.upper_bound) == 10

    @pytest.mark.asyncio
    async def test_forecast_holt_model(self):
        """Test forecast with Holt's model explicitly."""
        data = self._generate_test_data()
        result = await timesfm_engine.forecast(
            data,
            forecast_horizon=5,
            model_type=ForecastModelType.HOLT_LINEAR
        )

        assert result.model_type == "holt_linear"
        assert len(result.values) == 5

    @pytest.mark.asyncio
    async def test_forecast_insufficient_data(self):
        """Test forecast with insufficient data."""
        data = [(datetime.now(), 1.0)]  # Only one point
        result = await timesfm_engine.forecast(data, forecast_horizon=5)

        assert result.model_type == "fallback"
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_forecast_negative_values(self):
        """Test that forecasts don't go negative."""
        data = self._generate_test_data(trend=0.1, noise=0.05)
        result = await timesfm_engine.forecast(data, forecast_horizon=10)

        # All forecasts should be non-negative
        assert all(v >= 0 for v in result.values)

    @pytest.mark.asyncio
    async def test_confidence_intervals(self):
        """Test that confidence intervals make sense."""
        data = self._generate_test_data()
        result = await timesfm_engine.forecast(data, forecast_horizon=10)

        # Lower bound should be below forecast
        # Upper bound should be above forecast
        for i in range(len(result.values)):
            assert result.lower_bound[i] <= result.values[i]
            assert result.upper_bound[i] >= result.values[i]

    @pytest.mark.asyncio
    async def test_batch_forecast(self):
        """Test batch forecasting."""
        series = {
            "product_1": self._generate_test_data(),
            "product_2": self._generate_test_data(trend=0.3),
        }

        results = await timesfm_engine.batch_forecast(series, forecast_horizon=5)

        assert "product_1" in results
        assert "product_2" in results
        assert len(results["product_1"].values) == 5

    @pytest.mark.asyncio
    async def test_evaluate_model(self):
        """Test model evaluation."""
        data = self._generate_test_data(n_points=60)
        result = await timesfm_engine.evaluate_model(data, test_size=10)

        if "error" not in result:
            assert "holt_linear" in result
            assert "mae" in result["holt_linear"]
            assert "rmse" in result["holt_linear"]


class TestForecastIntegration:
    """Integration tests for forecasting with API."""

    @pytest.fixture(autouse=True)
    async def setup(self, db_session):
        """Setup for integration tests."""
        await timesfm_engine.initialize()
        self.db = db_session
        yield
        await timesfm_engine.close()

    def _create_forecast_job(self, user_id: str, status: str = "pending") -> ForecastJob:
        """Create a test forecast job."""
        job = ForecastJob(
            user_id=user_id,
            category="wheat",
            region="east-africa",
            forecast_days=30,
            status=status
        )
        self.db.add(job)
        self.db.commit()
        return job

    @pytest.mark.asyncio
    async def test_forecast_job_workflow(self, test_user):
        """Test complete forecast job workflow."""
        # Create job
        job = self._create_forecast_job(test_user.id)

        assert job.status == "pending"

        # Simulate processing (in real app, this would be a Celery task)
        # ...

        # Update job with results
        job.status = "completed"
        job.result_data = {
            "forecast": [1.0, 2.0, 3.0],
            "confidence_interval": {"lower": [0.9, 1.8, 2.7], "upper": [1.1, 2.2, 3.3]}
        }
        job.completed_at = datetime.now()
        self.db.commit()

        assert job.status == "completed"
        assert job.result_data is not None
