# ACAS v2 - Sentiment Package
"""Sentiment analysis and intelligence engine"""

from .sentiment_analyzer import sentiment_analyzer
from .intelligence_engine import intelligence_engine
from .news_aggregator import news_aggregator

__all__ = ["sentiment_analyzer", "intelligence_engine", "news_aggregator"]
