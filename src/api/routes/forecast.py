"""
ACAS v2 - Forecast API Routes
Sales prediction and inventory optimization
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.routes.auth import require_auth
from src.core.logging import get_logger
from src.ml.sales_predictor import (
    sales_predictor, ProductCategory, Region, SalesDataPoint
)

logger = get_logger(__name__)
router = APIRouter()


class SalesDataInput(BaseModel):
    timestamp: datetime
    amount: float = Field(gt=0)
    quantity: int = Field(gt=0)
    product_id: Optional[str] = None
    region: Optional[str] = None
    channel: Optional[str] = "online"


class ForecastRequest(BaseModel):
    category: str = Field(..., pattern="^(electronics|fashion|home|beauty|sports|food|other)$")
    region: str = Field(..., pattern="^(africa|mena|sea|china_nw|global)$")
    historical_data: List[SalesDataInput]
    forecast_days: int = Field(default=30, ge=7, le=365)


class InventoryRequest(BaseModel):
    product_id: str
    current_stock: int = Field(ge=0)
    lead_time_days: int = Field(ge=1, le=90)
    historical_sales: List[SalesDataInput]


class ForecastResponse(BaseModel):
    category: str
    region: str
    forecast: dict
    total_predicted_revenue: float
    total_predicted_units: int
    growth_rate: float
    confidence_score: float
    seasonality_detected: bool
    recommendations: List[str]


@router.post("/sales", response_model=ForecastResponse)
async def forecast_sales(
    request: ForecastRequest,
    user: dict = Depends(require_auth)
):
    """
    Generate sales forecast for a product category and region
    """
    try:
        category = ProductCategory(request.category)
        region = Region(request.region)
        
        # Convert input data
        sales_data = [
            SalesDataPoint(
                timestamp=d.timestamp,
                amount=d.amount,
                quantity=d.quantity,
                product_id=d.product_id,
                region=d.region,
                channel=d.channel
            )
            for d in request.historical_data
        ]
        
        if len(sales_data) < 30:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least 30 data points required for reliable forecasting"
            )
        
        result = await sales_predictor.predict_category_sales(
            category=category,
            region=region,
            historical_sales=sales_data,
            forecast_days=request.forecast_days
        )
        
        return ForecastResponse(
            category=category.value,
            region=region.value,
            forecast=result.forecast.to_dict(),
            total_predicted_revenue=result.total_predicted_revenue,
            total_predicted_units=result.total_predicted_units,
            growth_rate=result.growth_rate,
            confidence_score=result.confidence_score,
            seasonality_detected=result.seasonality_detected,
            recommendations=result.recommendations
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/inventory")
async def predict_inventory(
    request: InventoryRequest,
    user: dict = Depends(require_auth)
):
    """
    Predict inventory needs and stockout risk
    """
    sales_data = [
        SalesDataPoint(
            timestamp=d.timestamp,
            amount=d.amount,
            quantity=d.quantity
        )
        for d in request.historical_sales
    ]
    
    result = await sales_predictor.predict_inventory_needs(
        product_id=request.product_id,
        current_stock=request.current_stock,
        lead_time_days=request.lead_time_days,
        historical_sales=sales_data
    )
    
    return result


@router.get("/categories")
async def list_categories(user: dict = Depends(require_auth)):
    """List available product categories"""
    return {
        "categories": [c.value for c in ProductCategory],
        "regions": [r.value for r in Region]
    }
