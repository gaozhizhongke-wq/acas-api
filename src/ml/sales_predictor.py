"""
ACAS v2 - Sales Prediction Service
Business logic layer on top of TimesFM
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from enum import Enum

from .timesfm_engine import timesfm_engine, ForecastResult
from src.core.logging import get_logger

logger = get_logger(__name__)


class ProductCategory(Enum):
    """Product categories for specialized models"""
    ELECTRONICS = "electronics"
    FASHION = "fashion"
    HOME = "home"
    BEAUTY = "beauty"
    SPORTS = "sports"
    FOOD = "food"
    OTHER = "other"


class Region(Enum):
    """Sales regions"""
    AFRICA = "africa"
    MENA = "mena"  # Middle East & North Africa
    SEA = "sea"    # Southeast Asia
    CHINA_NW = "china_nw"
    GLOBAL = "global"


@dataclass
class SalesDataPoint:
    """Single sales data point"""
    timestamp: datetime
    amount: float
    quantity: int
    product_id: Optional[str] = None
    region: Optional[str] = None
    channel: Optional[str] = None  # online, retail, wholesale


@dataclass
class SalesForecast:
    """Complete sales forecast with business metrics"""
    product_category: ProductCategory
    region: Region
    forecast: ForecastResult
    total_predicted_revenue: float
    total_predicted_units: int
    growth_rate: float  # vs previous period
    confidence_score: float  # 0-1
    seasonality_detected: bool
    anomalies: List[Dict[str, Any]]
    recommendations: List[str]


class SalesPredictor:
    """
    High-level sales prediction service
    Integrates TimesFM with business logic
    """
    
    def __init__(self):
        self._engine = timesfm_engine
        self._initialized = False
        self._category_seasonality = {
            ProductCategory.ELECTRONICS: {"q4_boost": 1.5, "peak_months": [11, 12]},
            ProductCategory.FASHION: {"seasonal": True, "peak_months": [3, 6, 9, 12]},
            ProductCategory.FOOD: {"stable": True, "weekly_pattern": True},
        }
    
    async def initialize(self) -> bool:
        """Initialize prediction engine"""
        result = await self._engine.initialize()
        self._initialized = result
        return result
    
    async def predict_category_sales(
        self,
        category: ProductCategory,
        region: Region,
        historical_sales: List[SalesDataPoint],
        forecast_days: int = 30,
        include_recommendations: bool = True
    ) -> SalesForecast:
        """
        Generate sales forecast for a product category
        
        Args:
            category: Product category
            region: Sales region
            historical_sales: Historical sales data
            forecast_days: Days to forecast
            include_recommendations: Generate business recommendations
        """
        if not historical_sales:
            raise ValueError("Historical sales data required")
        
        # Aggregate daily sales
        daily_sales = self._aggregate_daily(historical_sales)
        
        # Generate forecast
        forecast_result = await self._engine.forecast(
            daily_sales,
            forecast_horizon=forecast_days,
            frequency="D"
        )
        
        # Calculate business metrics
        total_revenue = sum(forecast_result.values)
        avg_daily = total_revenue / forecast_days
        
        # Calculate growth rate
        recent_avg = sum(v for _, v in daily_sales[-30:]) / min(30, len(daily_sales))
        growth_rate = (avg_daily - recent_avg) / recent_avg if recent_avg > 0 else 0
        
        # Detect seasonality
        seasonality_detected = self._detect_seasonality(daily_sales, category)
        
        # Detect anomalies in forecast
        anomalies = self._detect_anomalies(forecast_result)
        
        # Generate recommendations
        recommendations = []
        if include_recommendations:
            recommendations = self._generate_recommendations(
                category, region, growth_rate, seasonality_detected, anomalies
            )
        
        return SalesForecast(
            product_category=category,
            region=region,
            forecast=forecast_result,
            total_predicted_revenue=total_revenue,
            total_predicted_units=int(total_revenue / 100),  # Assuming avg price
            growth_rate=growth_rate,
            confidence_score=self._calculate_confidence(forecast_result, len(daily_sales)),
            seasonality_detected=seasonality_detected,
            anomalies=anomalies,
            recommendations=recommendations
        )
    
    async def predict_demand_by_region(
        self,
        regions: List[Region],
        product_categories: List[ProductCategory],
        historical_data: Dict[str, List[SalesDataPoint]]
    ) -> Dict[str, SalesForecast]:
        """
        Multi-region demand forecasting
        """
        results = {}
        
        for region in regions:
            for category in product_categories:
                key = f"{region.value}_{category.value}"
                data = historical_data.get(key, [])
                
                if data:
                    try:
                        forecast = await self.predict_category_sales(
                            category, region, data
                        )
                        results[key] = forecast
                    except Exception as e:
                        logger.error(f"Forecast failed for {key}", exc_info=e)
        
        return results
    
    async def predict_inventory_needs(
        self,
        product_id: str,
        current_stock: int,
        lead_time_days: int,
        historical_sales: List[SalesDataPoint]
    ) -> Dict[str, Any]:
        """
        Predict inventory replenishment needs
        """
        # Forecast for lead time + safety buffer
        forecast_days = lead_time_days + 14
        
        daily_sales = self._aggregate_daily(historical_sales)
        forecast = await self._engine.forecast(
            daily_sales,
            forecast_horizon=forecast_days,
            frequency="D"
        )
        
        # Calculate needs
        predicted_demand = sum(forecast.values[:lead_time_days])
        safety_stock = sum(forecast.values[lead_time_days:]) * 0.5
        
        recommended_order = max(0, int(predicted_demand + safety_stock - current_stock))
        
        # Stockout risk
        stockout_risk = "high" if current_stock < predicted_demand * 0.8 else \
                       "medium" if current_stock < predicted_demand else "low"
        
        return {
            "product_id": product_id,
            "current_stock": current_stock,
            "predicted_demand_30d": sum(forecast.values[:30]),
            "predicted_demand_lead_time": predicted_demand,
            "recommended_order_quantity": recommended_order,
            "safety_stock_level": int(safety_stock),
            "stockout_risk": stockout_risk,
            "reorder_point": int(predicted_demand * 0.8),
            "forecast_confidence": self._calculate_confidence(forecast, len(daily_sales))
        }
    
    def _aggregate_daily(
        self,
        sales_data: List[SalesDataPoint]
    ) -> List[tuple]:
        """Aggregate sales to daily totals"""
        from collections import defaultdict
        
        daily = defaultdict(float)
        for point in sales_data:
            day = point.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            daily[day] += point.amount
        
        return sorted(daily.items())
    
    def _detect_seasonality(
        self,
        daily_sales: List[tuple],
        category: ProductCategory
    ) -> bool:
        """Detect if sales show seasonal patterns"""
        if len(daily_sales) < 60:
            return False
        
        # Simple seasonality detection using autocorrelation
        values = [v for _, v in daily_sales]
        
        # Check weekly pattern (7-day lag)
        if len(values) >= 14:
            weekly_corr = self._autocorrelation(values, 7)
            if weekly_corr > 0.3:
                return True
        
        # Check category-specific patterns
        cat_info = self._category_seasonality.get(category, {})
        if cat_info.get("seasonal"):
            return True
        
        return False
    
    def _autocorrelation(self, values: List[float], lag: int) -> float:
        """Calculate autocorrelation at given lag"""
        if len(values) <= lag:
            return 0
        
        mean = sum(values) / len(values)
        c0 = sum((x - mean) ** 2 for x in values) / len(values)
        
        if c0 == 0:
            return 0
        
        c_lag = sum(
            (values[i] - mean) * (values[i - lag] - mean)
            for i in range(lag, len(values))
        ) / (len(values) - lag)
        
        return c_lag / c0
    
    def _detect_anomalies(self, forecast: ForecastResult) -> List[Dict[str, Any]]:
        """Detect anomalous forecast points"""
        anomalies = []
        
        for i, (val, lower, upper) in enumerate(zip(
            forecast.values,
            forecast.lower_bound,
            forecast.upper_bound
        )):
            # Wide confidence interval indicates uncertainty
            relative_width = (upper - lower) / val if val > 0 else 0
            
            if relative_width > 0.5:  # >50% CI width
                anomalies.append({
                    "day": i + 1,
                    "predicted_value": val,
                    "uncertainty": relative_width,
                    "type": "high_uncertainty"
                })
        
        return anomalies
    
    def _calculate_confidence(
        self,
        forecast: ForecastResult,
        context_points: int
    ) -> float:
        """Calculate overall confidence score"""
        # Based on context length and CI width
        context_score = min(1.0, context_points / 365)  # Full year = 1.0
        
        avg_ci_width = sum(
            (u - l) / v if v > 0 else 0
            for v, l, u in zip(forecast.values, forecast.lower_bound, forecast.upper_bound)
        ) / len(forecast.values)
        
        ci_score = max(0, 1 - avg_ci_width)
        
        return (context_score * 0.4 + ci_score * 0.6)
    
    def _generate_recommendations(
        self,
        category: ProductCategory,
        region: Region,
        growth_rate: float,
        seasonality: bool,
        anomalies: List[Dict]
    ) -> List[str]:
        """Generate business recommendations"""
        recs = []
        
        if growth_rate > 0.2:
            recs.append(f"High growth detected ({growth_rate:.1%}). Consider increasing inventory.")
        elif growth_rate < -0.1:
            recs.append(f"Declining trend ({growth_rate:.1%}). Review pricing and marketing strategy.")
        
        if seasonality:
            recs.append("Seasonal pattern detected. Plan inventory and promotions accordingly.")
        
        if len(anomalies) > 3:
            recs.append(f"High forecast uncertainty ({len(anomalies)} days). Monitor closely.")
        
        # Category-specific
        if category == ProductCategory.ELECTRONICS:
            recs.append("Electronics: Consider Q4 holiday inventory buildup.")
        elif category == ProductCategory.FASHION:
            recs.append("Fashion: Align with seasonal collection launches.")
        
        # Region-specific
        if region == Region.AFRICA:
            recs.append("Africa: Consider mobile payment options.")
        elif region == Region.MENA:
            recs.append("MENA: Account for Ramadan seasonality.")
        
        return recs


# Global instance
sales_predictor = SalesPredictor()
