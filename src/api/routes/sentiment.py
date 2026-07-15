"""
ACAS v2 - Sentiment Analysis API Routes
Single text, batch, and aspect-level sentiment analysis
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.routes.auth import require_auth
from core.logging import get_logger
from sentiment.intelligence_engine import intelligence_engine

logger = get_logger(__name__)
router = APIRouter()


class SentimentRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description="Text to analyze")
    context: Optional[str] = Field(None, max_length=1000, description="Optional domain context")


class SentimentResponse(BaseModel):
    label: str
    score: float
    confidence: float
    aspects: dict
    model: str
    processing_time_ms: int


class BatchSentimentRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, max_length=100, description="List of texts to analyze")


class BatchSentimentResponse(BaseModel):
    results: List[SentimentResponse]
    total: int
    processing_time_ms: int


class AspectSentimentResponse(BaseModel):
    overall: SentimentResponse
    aspects: dict
    risk_indicators: dict
    summary: str


@router.post("/analyze", response_model=SentimentResponse)
async def analyze_sentiment(
    req: SentimentRequest,
    user: dict = Depends(require_auth)
):
    """Analyze sentiment of a single text"""
    result = await intelligence_engine._analyzer.analyze(req.text, context=req.context)
    return SentimentResponse(
        label=result.label.value,
        score=round(result.score, 4),
        confidence=round(result.confidence, 4),
        aspects={k: round(v, 4) for k, v in result.aspects.items()},
        model=result.model_used,
        processing_time_ms=result.processing_time_ms,
    )


@router.post("/batch", response_model=BatchSentimentResponse)
async def analyze_batch(
    req: BatchSentimentRequest,
    user: dict = Depends(require_auth)
):
    """Analyze sentiment of multiple texts in batch"""
    import time
    start = time.time()
    results = await intelligence_engine._analyzer.analyze_batch(req.texts)
    elapsed_ms = int((time.time() - start) * 1000)

    return BatchSentimentResponse(
        results=[
            SentimentResponse(
                label=r.label.value,
                score=round(r.score, 4),
                confidence=round(r.confidence, 4),
                aspects={k: round(v, 4) for k, v in r.aspects.items()},
                model=r.model_used,
                processing_time_ms=r.processing_time_ms,
            )
            for r in results
        ],
        total=len(results),
        processing_time_ms=elapsed_ms,
    )


@router.post("/aspects", response_model=AspectSentimentResponse)
async def analyze_with_aspects(
    req: SentimentRequest,
    user: dict = Depends(require_auth)
):
    """Analyze sentiment with aspect-level breakdown and risk indicators"""
    import time
    start = time.time()
    aspect_data = await intelligence_engine._analyzer.analyze_with_aspects(req.text)
    elapsed_ms = int((time.time() - start) * 1000)

    sentiment = aspect_data.get("sentiment", {})
    return AspectSentimentResponse(
        overall=SentimentResponse(
            label=sentiment.get("label", "neutral"),
            score=sentiment.get("score", 0.0),
            confidence=sentiment.get("confidence", 0.0),
            aspects=sentiment.get("aspects", {}),
            model=sentiment.get("model", "unknown"),
            processing_time_ms=sentiment.get("processing_time_ms", 0),
        ),
        aspects={k: round(v, 4) if isinstance(v, float) else v for k, v in sentiment.get("aspects", {}).items()},
        risk_indicators=aspect_data.get("risk_indicators", {}),
        summary=aspect_data.get("summary", ""),
    )
