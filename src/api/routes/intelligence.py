"""
ACAS v2 - Intelligence API Routes
WorldMonitor-style market intelligence and alerts
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.routes.auth import require_auth
from src.core.logging import get_logger
from src.sentiment.intelligence_engine import (
    intelligence_engine, RiskLevel, AlertType
)

logger = get_logger(__name__)
router = APIRouter()


class MarketIntelligenceResponse(BaseModel):
    timestamp: str
    overall_sentiment: float
    sentiment_trend: str
    risk_alerts: List[dict]
    top_topics: List[dict]
    regional_breakdown: dict
    commodity_sentiment: dict
    news_volume: int
    anomaly_detected: bool


class AlertResponse(BaseModel):
    id: str
    type: str
    level: str
    title: str
    description: str
    affected_regions: List[str]
    affected_commodities: List[str]
    created_at: str
    expires_at: Optional[str]
    actions_recommended: List[str]
    sentiment_trend: str


@router.get("/market", response_model=MarketIntelligenceResponse)
async def get_market_intelligence(
    regions: Optional[List[str]] = Query(None),
    commodities: Optional[List[str]] = Query(None),
    user: dict = Depends(require_auth)
):
    """
    Get comprehensive market intelligence
    """
    intelligence = await intelligence_engine.analyze_market(
        regions=regions,
        commodities=commodities
    )
    
    return MarketIntelligenceResponse(
        timestamp=intelligence.timestamp.isoformat(),
        overall_sentiment=intelligence.overall_sentiment,
        sentiment_trend=intelligence.sentiment_trend,
        risk_alerts=[
            {
                "id": a.id,
                "type": a.type.value,
                "level": a.level.name,
                "title": a.title,
                "description": a.description
            }
            for a in intelligence.risk_alerts
        ],
        top_topics=intelligence.top_topics,
        regional_breakdown=intelligence.regional_breakdown,
        commodity_sentiment=intelligence.commodity_sentiment,
        news_volume=intelligence.news_volume,
        anomaly_detected=intelligence.anomaly_detected
    )


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    min_level: str = Query("LOW", pattern="^(CRITICAL|HIGH|MEDIUM|LOW|INFO)$"),
    alert_type: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """
    Get active risk alerts
    """
    min_risk_level = RiskLevel[min_level]
    alerts = intelligence_engine.get_active_alerts(min_level=min_risk_level)
    
    if alert_type:
        alerts = [a for a in alerts if a.type.value == alert_type]
    
    return [
        AlertResponse(
            id=a.id,
            type=a.type.value,
            level=a.level.name,
            title=a.title,
            description=a.description,
            affected_regions=a.affected_regions,
            affected_commodities=a.affected_commodities,
            created_at=a.created_at.isoformat(),
            expires_at=a.expires_at.isoformat() if a.expires_at else None,
            actions_recommended=a.actions_recommended,
            sentiment_trend=a.sentiment_trend
        )
        for a in alerts
    ]


@router.get("/alerts/{alert_id}")
async def get_alert_detail(
    alert_id: str,
    user: dict = Depends(require_auth)
):
    """
    Get detailed information about a specific alert
    """
    alerts = intelligence_engine.get_active_alerts()
    alert = next((a for a in alerts if a.id == alert_id), None)
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return AlertResponse(
        id=alert.id,
        type=alert.type.value,
        level=alert.level.name,
        title=alert.title,
        description=alert.description,
        affected_regions=alert.affected_regions,
        affected_commodities=alert.affected_commodities,
        created_at=alert.created_at.isoformat(),
        expires_at=alert.expires_at.isoformat() if alert.expires_at else None,
        actions_recommended=alert.actions_recommended,
        sentiment_trend=alert.sentiment_trend
    )


@router.post("/monitor/start")
async def start_monitoring(
    interval_minutes: int = Query(5, ge=1, le=60),
    user: dict = Depends(require_auth)
):
    """
    Start continuous market monitoring
    """
    import asyncio
    
    # Run in background
    asyncio.create_task(
        intelligence_engine.start_monitoring(interval_seconds=interval_minutes * 60)
    )
    
    return {"status": "monitoring_started", "interval_minutes": interval_minutes}


@router.post("/monitor/stop")
async def stop_monitoring(user: dict = Depends(require_auth)):
    """
    Stop continuous monitoring
    """
    intelligence_engine.stop_monitoring()
    return {"status": "monitoring_stopped"}
