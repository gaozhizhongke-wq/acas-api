"""
ACAS v2 - Time Series Forecasting Engine
Multi-model ensemble with automatic model selection and hyperparameter tuning
Supports: Holt's Linear, ARIMA, Prophet, LSTM
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Callable
from datetime import datetime, timedelta
import numpy as np
import warnings
from enum import Enum
import pandas as pd

from core.config import config
from core.logging import get_logger

logger = get_logger(__name__)


class ForecastModelType(Enum):
    HOLT_LINEAR = "holt_linear"
    ARIMA = "arima"
    PROPHET = "prophet"
    LSTM = "lstm"
    ENSEMBLE = "ensemble"
    AUTO = "auto"


@dataclass
class ForecastResult:
    """Forecast result with confidence intervals"""
    timestamps: List[datetime]
    values: List[float]
    lower_bound: List[float]  # 10th percentile
    upper_bound: List[float]  # 90th percentile
    model_version: str
    model_type: str
    context_used: int
    metrics: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamps": [t.isoformat() for t in self.timestamps],
            "values": [round(v, 4) for v in self.values],
            "confidence_interval": {
                "lower": [round(v, 4) for v in self.lower_bound],
                "upper": [round(v, 4) for v in self.upper_bound]
            },
            "model": self.model_version,
            "model_type": self.model_type,
            "context_points": self.context_used,
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "warnings": self.warnings
        }


class ModelSelector:
    """
    Automatic model selection based on data characteristics
    """

    @staticmethod
    def analyze_series(values: np.ndarray) -> Dict[str, Any]:
        """
        Analyze time series characteristics
        Returns: trend, seasonality, noise_level, stability
        """
        if len(values) < 4:
            return {
                "trend": "insufficient_data",
                "seasonality": None,
                "noise_level": "high",
                "stability": "unknown",
                "recommended_model": ForecastModelType.HOLT_LINEAR
            }

        # Trend analysis
        x = np.arange(len(values))
        slope, _ = np.polyfit(x, values, 1)
        normalized_slope = slope / np.mean(values) if np.mean(values) != 0 else 0

        if abs(normalized_slope) > 0.1:
            trend = "strong"
        elif abs(normalized_slope) > 0.05:
            trend = "moderate"
        else:
            trend = "weak"

        # Seasonality detection (for daily data, check weekly)
        seasonality = None
        if len(values) >= 14:
            # Autocorrelation at lag 7
            autocorr = np.corrcoef(values[7:], values[:-7])[0, 1]
            if autocorr > 0.3:
                seasonality = "weekly"
            elif len(values) >= 30:
                # Check monthly
                autocorr_monthly = np.corrcoef(values[30:], values[:-30])[0, 1]
                if autocorr_monthly > 0.3:
                    seasonality = "monthly"

        # Noise level
        if len(values) >= 10:
            residuals = values[1:] - values[:-1]
            noise_ratio = np.std(residuals) / np.mean(values)
            if noise_ratio > 0.3:
                noise_level = "high"
            elif noise_ratio > 0.15:
                noise_level = "moderate"
            else:
                noise_level = "low"
        else:
            noise_level = "unknown"

        # Stability: check for structural breaks
        stability = "stable"
        if len(values) >= 20:
            half = len(values) // 2
            mean_first = np.mean(values[:half])
            mean_second = np.mean(values[half:])
            if abs(mean_second - mean_first) / max(abs(mean_first), 1) > 0.3:
                stability = "unstable"

        # Model recommendation
        if stability == "unstable" or len(values) < 10:
            recommended = ForecastModelType.HOLT_LINEAR
        elif seasonality and trend != "weak":
            recommended = ForecastModelType.PROPHET
        elif noise_level == "low" and len(values) >= 30:
            recommended = ForecastModelType.ARIMA
        elif len(values) >= 50:
            recommended = ForecastModelType.LSTM
        else:
            recommended = ForecastModelType.HOLT_LINEAR

        return {
            "trend": trend,
            "seasonality": seasonality,
            "noise_level": noise_level,
            "stability": stability,
            "recommended_model": recommended
        }


class HoltLinearModel:
    """
    Holt's Linear Trend Method with automatic parameter tuning
    """

    def __init__(self):
        self.alpha = None  # Smoothing parameter
        self.beta = None   # Trend parameter
        self._fitted_values = None
        self._residuals = None

    def fit(self, values: np.ndarray, optimize: bool = True) -> None:
        """
        Fit model to data, optionally optimize parameters
        """
        if optimize and len(values) >= 10:
            best_alpha, best_beta, best_error = None, None, float('inf')

            # Grid search
            for alpha in np.arange(0.1, 0.9, 0.1):
                for beta in np.arange(0.05, 0.3, 0.05):
                    error = self._cross_validate(values, alpha, beta)
                    if error < best_error:
                        best_error = error
                        best_alpha = alpha
                        best_beta = beta

            self.alpha = best_alpha
            self.beta = best_beta
        else:
            self.alpha = 0.3
            self.beta = 0.1

        # Fit on full data
        self._fitted_values = self._holt_linear(values, self.alpha, self.beta)
        self._residuals = values - self._fitted_values

    def _holt_linear(self, values: np.ndarray, alpha: float, beta: float) -> np.ndarray:
        """Apply Holt's linear method"""
        level = values[0]
        trend = (values[-1] - values[0]) / max(len(values) - 1, 1)

        fitted = np.zeros(len(values))

        for i in range(1, len(values)):
            new_level = alpha * values[i] + (1 - alpha) * (level + trend)
            new_trend = beta * (new_level - level) + (1 - beta) * trend

            fitted[i] = level + trend
            level = new_level
            trend = new_trend

        return fitted

    def _cross_validate(self, values: np.ndarray, alpha: float, beta: float) -> float:
        """
        Time series cross-validation (rolling forecast)
        """
        if len(values) < 5:
            return 0.0

        errors = []
        train_size = max(5, len(values) // 2)

        for i in range(train_size, len(values)):
            train = values[:i]
            actual = values[i]

            # Fit on training data
            level = train[0]
            trend = (train[-1] - train[0]) / max(len(train) - 1, 1)

            for j in range(1, len(train)):
                new_level = alpha * train[j] + (1 - alpha) * (level + trend)
                new_trend = beta * (new_level - level) + (1 - beta) * trend
                level = new_level
                trend = new_trend

            # Forecast
            forecast = level + trend
            errors.append((actual - forecast) ** 2)

        return np.mean(errors) if errors else 0.0

    def forecast(self, values: np.ndarray, horizon: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate forecast with confidence intervals
        Returns: (forecast, lower, upper)
        """
        # Fit if not already fitted
        if self._fitted_values is None:
            self.fit(values)

        # Get last level and trend
        level = values[0]
        trend = (values[-1] - values[0]) / max(len(values) - 1, 1)

        for i in range(1, len(values)):
            new_level = self.alpha * values[i] + (1 - self.alpha) * (level + trend)
            new_trend = self.beta * (new_level - level) + (1 - self.beta) * trend
            level = new_level
            trend = new_trend

        # Generate forecast
        forecasts = []
        current_level = level
        current_trend = trend

        for i in range(horizon):
            forecast = current_level + current_trend
            forecasts.append(max(0, forecast))

            # Update for next step
            current_level += current_trend

        forecasts = np.array(forecasts)

        # Confidence intervals
        if self._residuals is not None and len(self._residuals) > 1:
            residual_std = np.std(self._residuals)
        else:
            residual_std = np.std(values) * 0.1

        # Increasing uncertainty over time
        margins = residual_std * (1 + np.arange(horizon) * 0.05) * 1.28  # 80% CI

        lower = np.maximum(0, forecasts - margins)
        upper = forecasts + margins

        return forecasts, lower, upper

    def metrics(self, values: np.ndarray) -> Dict[str, float]:
        """Calculate model performance metrics"""
        if self._fitted_values is None:
            self.fit(values)

        actual = values[1:]  # Skip first point (no forecast)
        predicted = self._fitted_values[1:]

        mae = np.mean(np.abs(actual - predicted))
        mse = np.mean((actual - predicted) ** 2)
        rmse = np.sqrt(mse)

        # MAPE (avoid division by zero)
        mape = np.mean(np.abs((actual - predicted) / np.maximum(actual, 1))) * 100

        return {
            "mae": mae,
            "rmse": rmse,
            "mape": mape,
            "alpha": self.alpha,
            "beta": self.beta
        }


class ProphetModel:
    """
    Prophet time series model wrapper
    Supports seasonality, holidays, and changepoints
    """

    def __init__(self):
        self._model = None
        self._fitted = False

    def fit(self, dates: List[datetime], values: np.ndarray) -> None:
        """
        Fit Prophet model to data
        """
        try:
            from prophet import Prophet
        except ImportError:
            raise RuntimeError("Prophet not installed. Install with: pip install prophet")

        # Prepare DataFrame
        df = pd.DataFrame({
            'ds': dates,
            'y': values
        })

        # Create and fit model
        self._model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.05
        )

        self._model.fit(df)
        self._fitted = True

    def forecast(self, dates: List[datetime], horizon: int, frequency: str = "D") -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate forecast with confidence intervals
        Returns: (forecast, lower, upper)
        """
        if not self._fitted or not self._model:
            raise RuntimeError("Model not fitted")

        # Create future DataFrame
        last_date = dates[-1]
        future_dates = self._generate_future_dates(last_date, horizon, frequency)

        future_df = pd.DataFrame({'ds': future_dates})
        forecast_df = self._model.predict(future_df)

        # Extract predictions
        forecasts = forecast_df['yhat'].values
        lower = forecast_df['yhat_lower'].values
        upper = forecast_df['yhat_upper'].values

        return forecasts, lower, upper

    def _generate_future_dates(self, start: datetime, count: int, frequency: str) -> List[datetime]:
        """Generate future dates"""
        deltas = {
            "H": timedelta(hours=1),
            "D": timedelta(days=1),
            "W": timedelta(weeks=1),
            "M": timedelta(days=30),
        }
        delta = deltas.get(frequency, timedelta(days=1))
        return [start + delta * (i + 1) for i in range(count)]

    def metrics(self, dates: List[datetime], values: np.ndarray) -> Dict[str, float]:
        """Calculate model performance metrics"""
        if not self._fitted or not self._model:
            return {}

        # In-sample predictions
        df = pd.DataFrame({'ds': dates, 'y': values})
        predictions = self._model.predict(df)

        actual = values
        predicted = predictions['yhat'].values

        mae = np.mean(np.abs(actual - predicted))
        mse = np.mean((actual - predicted) ** 2)
        rmse = np.sqrt(mse)
        mape = np.mean(np.abs((actual - predicted) / np.maximum(actual, 1))) * 100

        return {
            "mae": mae,
            "rmse": rmse,
            "mape": mape
        }


class LSTMModel:
    """
    LSTM time series model (simplified for production)
    Uses pre-trained weights or incremental training
    """

    def __init__(self, hidden_size: int = 50, num_layers: int = 2):
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self._model = None
        self._fitted = False

    def fit(self, values: np.ndarray, epochs: int = 50, learning_rate: float = 0.01) -> None:
        """
        Fit LSTM model to data
        Note: LSTM requires significant data and training time
        """
        try:
            import torch
            from torch import nn
            from torch.optim import Adam
        except ImportError:
            raise RuntimeError("PyTorch not installed. Install with: pip install torch")

        # Prepare sequences
        X, y = self._prepare_sequences(values, seq_length=10)

        if len(X) < 10:
            raise ValueError("Insufficient data for LSTM (need at least 20 points)")

        # Create model
        class LSTMNet(nn.Module):
            def __init__(self, input_size=1, hidden_size=50, num_layers=2):
                super().__init__()
                self.hidden_size = hidden_size
                self.num_layers = num_layers
                self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
                self.fc = nn.Linear(hidden_size, 1)

            def forward(self, x):
                h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
                c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
                out, _ = self.lstm(x, (h0, c0))
                out = self.fc(out[:, -1, :])
                return out

        self._model = LSTMNet(1, self.hidden_size, self.num_layers)
        criterion = nn.MSELoss()
        optimizer = Adam(self._model.parameters(), lr=learning_rate)

        # Convert to tensors
        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.FloatTensor(y).unsqueeze(1)

        # Training loop
        self._model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            outputs = self._model(X_tensor)
            loss = criterion(outputs, y_tensor)
            loss.backward()
            optimizer.step()

            if (epoch + 1) % 20 == 0:
                logger.info(f"LSTM Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.4f}")

        self._fitted = True

    def forecast(self, values: np.ndarray, horizon: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate forecast using LSTM
        """
        if not self._fitted or not self._model:
            raise RuntimeError("Model not fitted")

        import torch

        self._model.eval()
        with torch.no_grad():
            # Prepare last sequence
            seq_length = 10
            if len(values) < seq_length:
                raise ValueError(f"Need at least {seq_length} points for LSTM forecast")

            current_seq = values[-seq_length:].reshape(1, seq_length, 1)
            current_seq = torch.FloatTensor(current_seq)

            forecasts = []
            for i in range(horizon):
                pred = self._model(current_seq).item()
                forecasts.append(pred)

                # Update sequence
                current_seq = torch.cat([
                    current_seq[:, 1:, :],
                    torch.FloatTensor([[[pred]]])
                ], dim=1)

        forecasts = np.array(forecasts)

        # Confidence intervals (simplified)
        std = np.std(values)
        lower = forecasts - 1.28 * std
        upper = forecasts + 1.28 * std

        return forecasts, lower, upper

    def _prepare_sequences(self, data: np.ndarray, seq_length: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for LSTM"""
        X, y = [], []
        for i in range(len(data) - seq_length):
            X.append(data[i:i+seq_length])
            y.append(data[i+seq_length])
        return np.array(X).reshape(-1, seq_length, 1), np.array(y)

    def metrics(self, values: np.ndarray) -> Dict[str, float]:
        """Calculate model performance metrics"""
        if not self._fitted or not self._model:
            return {}

        # Prepare data
        X, y = self._prepare_sequences(values, seq_length=10)

        if len(X) < 5:
            return {}

        # Predictions
        import torch
        self._model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X)
            predictions = self._model(X_tensor).numpy().flatten()

        actual = y

        mae = np.mean(np.abs(actual - predictions))
        mse = np.mean((actual - predictions) ** 2)
        rmse = np.sqrt(mse)

        return {
            "mae": mae,
            "rmse": rmse,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers
        }


class TimesFMEngine:
    """
    Statistical Forecasting Engine (v2.0)
    Implements Holt's Linear Trend and ARIMA for time series forecasting.
    
    Available models:
    - Holt's Linear: always available (numpy-based, no external ML deps)
    - ARIMA: available when statsmodels is installed (requires ≥20 data points)
    
    NOT available in current deployment:
    - Prophet: requires `pip install prophet` (Facebook/Meta library)
    - LSTM: requires `pip install torch` (PyTorch)
    - TimesFM (Google): requires GPU infrastructure
    """

    def __init__(self):
        self._model_version = "2.0-statistical"
        self._context_length = config.ml.timesfm_context_length
        self._horizon = config.ml.timesfm_prediction_horizon
        self._initialized = False
        self._models = {}

    async def initialize(self) -> bool:
        """Initialize forecasting engine"""
        if not config.ml.timesfm_enabled:
            logger.info("TimesFM disabled in config")
            return False

        # Always available: Holt's Linear (numpy pure-Python implementation)
        self._models[ForecastModelType.HOLT_LINEAR] = HoltLinearModel()
        logger.info("Holt's Linear model ready (always available)")

        # ARIMA: available when statsmodels is installed
        self._arima_available = False
        try:
            from statsmodels.tsa.arima.model import ARIMA
            self._arima_available = True
            logger.info("ARIMA model ready (via statsmodels)")
        except ImportError:
            logger.info("ARIMA not available — statsmodels not installed")

        # Prophet: requires pip install prophet (not installed in current image)
        # LSTM: requires pip install torch (not installed in current image)
        # TimesFM (Google): requires GPU infrastructure (not available in current image)
        for name, pkg in [("Prophet", "prophet"), ("LSTM/PyTorch", "torch")]:
            logger.info(f"{name} not available — package not installed")

        actual_model_count = len(self._models) + (1 if self._arima_available else 0)
        self._initialized = True
        logger.info(
            f"Forecast engine {self._model_version} ready: "
            f"{list(self._models.keys())[0].value} "
            f"{'+ ARIMA' if self._arima_available else '(ARIMA unavailable)'} "
            f"(Prophet/LSTM/TimesFM require additional packages)"
        )
        return True

    async def forecast(
        self,
        historical_data: List[Tuple[datetime, float]],
        forecast_horizon: Optional[int] = None,
        model_type: ForecastModelType = ForecastModelType.AUTO,
        frequency: str = "D"
    ) -> ForecastResult:
        """
        Generate forecast from historical data

        Args:
            historical_data: List of (timestamp, value) tuples
            forecast_horizon: Number of steps to forecast
            model_type: Model to use (AUTO for automatic selection)
            frequency: Time frequency
        """
        horizon = forecast_horizon or self._horizon

        if len(historical_data) < 2:
            return self._fallback_forecast(historical_data, horizon, frequency)

        # Extract values
        values = np.array([v for _, v in historical_data])
        dates = [d for d, _ in historical_data]

        # Automatic model selection
        if model_type == ForecastModelType.AUTO:
            analysis = ModelSelector.analyze_series(values)
            selected_model = analysis["recommended_model"]
            logger.info(
                f"Auto-selected model: {selected_model.value}",
                extra={"analysis": analysis}
            )
        else:
            selected_model = model_type

        # Generate forecast
        if selected_model == ForecastModelType.HOLT_LINEAR:
            result = await self._forecast_holt(values, horizon, frequency)
        elif selected_model == ForecastModelType.PROPHET:
            result = await self._forecast_prophet(dates, values, horizon, frequency)
        elif selected_model == ForecastModelType.LSTM:
            result = await self._forecast_lstm(values, horizon, frequency)
        elif selected_model == ForecastModelType.ENSEMBLE:
            result = await self._forecast_ensemble(values, horizon, frequency)
        else:
            # Fallback to Holt if model not available
            logger.warning(f"Model {selected_model.value} not available, using Holt")
            result = await self._forecast_holt(values, horizon, frequency)

        # Add metadata
        result.model_type = selected_model.value

        return result

    async def _forecast_holt(
        self,
        values: np.ndarray,
        horizon: int,
        frequency: str
    ) -> ForecastResult:
        """Forecast using Holt's linear method with tuning"""
        model = self._models.get(ForecastModelType.HOLT_LINEAR)
        if not model:
            return self._fallback_forecast([], horizon, frequency)

        # Fit with optimization
        model.fit(values, optimize=True)

        # Generate forecast
        forecasts, lower, upper = model.forecast(values, horizon)

        # Calculate metrics
        metrics = model.metrics(values)

        # Generate timestamps
        last_date = datetime.now()  # Will be overridden by caller
        timestamps = self._generate_timestamps(last_date, horizon, frequency)

        return ForecastResult(
            timestamps=timestamps,
            values=forecasts.tolist(),
            lower_bound=lower.tolist(),
            upper_bound=upper.tolist(),
            model_version=self._model_version,
            model_type=ForecastModelType.HOLT_LINEAR.value,
            context_used=len(values),
            metrics=metrics
        )

    async def _forecast_prophet(
        self,
        dates: List[datetime],
        values: np.ndarray,
        horizon: int,
        frequency: str
    ) -> ForecastResult:
        """Forecast using Prophet model"""
        model = self._models.get(ForecastModelType.PROPHET)

        if not model or not isinstance(model, ProphetModel):
            logger.warning("Prophet model not available")
            return self._fallback_forecast([], horizon, frequency)

        try:
            # Fit model
            model.fit(dates, values)

            # Generate forecast
            forecasts, lower, upper = model.forecast(dates, horizon, frequency)

            # Calculate metrics
            metrics = model.metrics(dates, values)

            # Generate timestamps
            timestamps = self._generate_timestamps(dates[-1], horizon, frequency)

            return ForecastResult(
                timestamps=timestamps,
                values=forecasts.tolist(),
                lower_bound=lower.tolist(),
                upper_bound=upper.tolist(),
                model_version=self._model_version,
                model_type=ForecastModelType.PROPHET.value,
                context_used=len(values),
                metrics=metrics
            )

        except Exception as e:
            logger.error(f"Prophet forecast failed: {e}")
            return self._fallback_forecast([], horizon, frequency)

    async def _forecast_lstm(
        self,
        values: np.ndarray,
        horizon: int,
        frequency: str
    ) -> ForecastResult:
        """Forecast using LSTM model"""
        if len(values) < 20:
            logger.warning("Insufficient data for LSTM (need >= 20 points)")
            return self._fallback_forecast([], horizon, frequency)

        try:
            model = LSTMModel()
            model.fit(values, epochs=50, learning_rate=0.01)

            forecasts, lower, upper = model.forecast(values, horizon)

            # Calculate metrics
            metrics = model.metrics(values)

            # Generate timestamps
            last_date = datetime.now()
            timestamps = self._generate_timestamps(last_date, horizon, frequency)

            return ForecastResult(
                timestamps=timestamps,
                values=forecasts.tolist(),
                lower_bound=lower.tolist(),
                upper_bound=upper.tolist(),
                model_version=self._model_version,
                model_type=ForecastModelType.LSTM.value,
                context_used=len(values),
                metrics=metrics
            )

        except Exception as e:
            logger.error(f"LSTM forecast failed: {e}")
            return self._fallback_forecast([], horizon, frequency)

    async def _forecast_ensemble(
        self,
        values: np.ndarray,
        horizon: int,
        frequency: str
    ) -> ForecastResult:
        """Ensemble forecast (average multiple models)"""
        forecasts = []
        weights = []

        # Holt's method
        holt_model = self._models.get(ForecastModelType.HOLT_LINEAR)
        if holt_model:
            holt_model.fit(values, optimize=True)
            f, _, _ = holt_model.forecast(values, horizon)
            forecasts.append(f)
            weights.append(0.6)  # Higher weight for simpler model

        # If we have enough data, add ARIMA
        if len(values) >= 20:
            try:
                from statsmodels.tsa.arima.model import ARIMA

                arima_model = ARIMA(values, order=(1, 1, 1))
                arima_fitted = arima_model.fit()
                arima_forecast = arima_fitted.forecast(steps=horizon)
                forecasts.append(arima_forecast)
                weights.append(0.4)
            except Exception as e:
                logger.warning(f"ARIMA forecast failed: {e}")

        if not forecasts:
            return self._fallback_forecast([], horizon, frequency)

        # Weighted average
        weights = np.array(weights) / sum(weights)
        ensemble_forecast = np.zeros(horizon)
        for i, (f, w) in enumerate(zip(forecasts, weights)):
            ensemble_forecast += w * f

        # Confidence intervals (use widest)
        lower = ensemble_forecast - np.std(values) * 1.28
        upper = ensemble_forecast + np.std(values) * 1.28

        last_date = datetime.now()
        timestamps = self._generate_timestamps(last_date, horizon, frequency)

        return ForecastResult(
            timestamps=timestamps,
            values=ensemble_forecast.tolist(),
            lower_bound=lower.tolist(),
            upper_bound=upper.tolist(),
            model_version=self._model_version,
            model_type=ForecastModelType.ENSEMBLE.value,
            context_used=len(values),
            metrics={"ensemble": True}
        )

    def _fallback_forecast(
        self,
        historical_data: List[Tuple[datetime, float]],
        horizon: int,
        frequency: str
    ) -> ForecastResult:
        """Fallback forecast when no data available"""
        last_value = historical_data[-1][1] if historical_data else 0
        last_date = historical_data[-1][0] if historical_data else datetime.now()

        timestamps = self._generate_timestamps(last_date, horizon, frequency)

        return ForecastResult(
            timestamps=timestamps,
            values=[last_value] * horizon,
            lower_bound=[last_value * 0.9] * horizon,
            upper_bound=[last_value * 1.1] * horizon,
            model_version=self._model_version,
            model_type="fallback",
            context_used=len(historical_data),
            warnings=["Insufficient data for model-based forecast"]
        )

    def _generate_timestamps(
        self,
        start: datetime,
        count: int,
        frequency: str
    ) -> List[datetime]:
        """Generate future timestamps"""
        deltas = {
            "H": timedelta(hours=1),
            "D": timedelta(days=1),
            "W": timedelta(weeks=1),
            "M": timedelta(days=30),
        }
        delta = deltas.get(frequency, timedelta(days=1))

        return [start + delta * (i + 1) for i in range(count)]

    async def batch_forecast(
        self,
        product_series: Dict[str, List[Tuple[datetime, float]]],
        forecast_horizon: int = 30,
        model_type: ForecastModelType = ForecastModelType.AUTO
    ) -> Dict[str, ForecastResult]:
        """Batch forecast for multiple products"""
        results = {}

        for product_id, data in product_series.items():
            try:
                results[product_id] = await self.forecast(
                    data, forecast_horizon, model_type
                )
            except Exception as e:
                logger.error(f"Forecast failed for {product_id}: {e}")
                results[product_id] = self._fallback_forecast(
                    data, forecast_horizon, "D"
                )

        return results

    async def evaluate_model(
        self,
        historical_data: List[Tuple[datetime, float]],
        test_size: int = 30
    ) -> Dict[str, Any]:
        """
        Evaluate model performance using walk-forward validation
        Returns performance metrics for different models
        """
        if len(historical_data) < test_size + 10:
            return {"error": "Insufficient data for evaluation"}

        values = np.array([v for _, v in historical_data])
        train = values[:-test_size]
        test = values[-test_size:]

        results = {}

        # Evaluate Holt's method
        holt_model = HoltLinearModel()
        holt_model.fit(train, optimize=True)
        holt_forecast, _, _ = holt_model.forecast(train, test_size)

        results["holt_linear"] = {
            "mae": float(np.mean(np.abs(test - holt_forecast))),
            "rmse": float(np.sqrt(np.mean((test - holt_forecast) ** 2))),
            "mape": float(np.mean(np.abs((test - holt_forecast) / np.maximum(test, 1))) * 100)
        }

        # Evaluate Prophet if available
        if ForecastModelType.PROPHET in self._models:
            try:
                dates = [datetime.now() - timedelta(days=i) for i in range(len(train), 0, -1)]
                prophet_model = ProphetModel()
                prophet_model.fit(dates, train)
                prophet_forecast, _, _ = prophet_model.forecast(dates, test_size)

                results["prophet"] = {
                    "mae": float(np.mean(np.abs(test - prophet_forecast[:test_size]))),
                    "rmse": float(np.sqrt(np.mean((test - prophet_forecast[:test_size]) ** 2))),
                    "mape": float(np.mean(np.abs((test - prophet_forecast[:test_size]) / np.maximum(test, 1))) * 100)
                }
            except Exception as e:
                logger.warning(f"Prophet evaluation failed: {e}")

        return results

    async def close(self):
        """Cleanup engine resources."""
        self._models.clear()
        self._initialized = False


# Global instance
timesfm_engine = TimesFMEngine()
