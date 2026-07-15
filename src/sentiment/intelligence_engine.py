"""
ACAS v2 - Intelligence Engine
WorldMonitor-style risk assessment and alerting
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from enum import Enum
import asyncio

from .news_aggregator import NewsAggregator, NewsArticle, NewsCategory, news_aggregator
from .sentiment_analyzer import SentimentAnalyzer, SentimentResult, sentiment_analyzer
from core.logging import get_logger

logger = get_logger(__name__)


class RiskLevel(Enum):
    CRITICAL = 5    # Immediate action required
    HIGH = 4        # Significant impact likely
    MEDIUM = 3      # Monitor closely
    LOW = 2         # Awareness needed
    INFO = 1        # Informational


class AlertType(Enum):
    SUPPLY_CHAIN = "supply_chain"
    PRICE_MOVEMENT = "price_movement"
    GEOPOLITICAL = "geopolitical"
    REGULATORY = "regulatory"
    NATURAL_DISASTER = "natural_disaster"
    MARKET_SENTIMENT = "market_sentiment"


@dataclass
class RiskAlert:
    """Risk alert with context"""
    id: str
    type: AlertType
    level: RiskLevel
    title: str
    description: str
    affected_regions: List[str]
    affected_commodities: List[str]
    source_articles: List[str]
    created_at: datetime
    expires_at: Optional[datetime] = None
    actions_recommended: List[str] = field(default_factory=list)
    sentiment_trend: str = "neutral"  # improving, deteriorating, stable


@dataclass
class MarketIntelligence:
    """Aggregated market intelligence"""
    timestamp: datetime
    overall_sentiment: float
    sentiment_trend: str
    risk_alerts: List[RiskAlert]
    top_topics: List[Dict]
    regional_breakdown: Dict[str, float]
    commodity_sentiment: Dict[str, float]
    news_volume: int
    anomaly_detected: bool


class IntelligenceEngine:
    """
    WorldMonitor-style intelligence engine
    - Real-time news monitoring
    - Multi-dimensional risk scoring
    - Automated alerting
    """
    
    # Risk scoring weights
    SENTIMENT_WEIGHT = 0.3
    VOLUME_WEIGHT = 0.2
    SOURCE_WEIGHT = 0.2
    KEYWORD_WEIGHT = 0.3
    
    # Trusted sources get higher weight
    TRUSTED_SOURCES = {
        "Reuters": 1.0,
        "Bloomberg": 1.0,
        "CNBC": 0.9,
        "BBC": 0.9,
        "Financial Times": 0.95,
    }
    
    def __init__(self):
        self._aggregator = news_aggregator
        self._analyzer = sentiment_analyzer
        self._alerts: List[RiskAlert] = []
        self._monitoring = False
    
    async def initialize(self) -> None:
        """Initialize engine — only start sub-components that are enabled."""
        from core.config import config as ml_config
        # Initialize news aggregator (always safe, just HTTP calls)
        await self._aggregator.initialize()
        # Only initialize sentiment analyzer if enabled
        if ml_config.ml.sentiment_enabled:
            await self._analyzer.initialize()
            logger.info("Intelligence engine initialized (sentiment: ML)")
        else:
            logger.info("Intelligence engine initialized (sentiment: disabled)")
    
    async def close(self) -> None:
        """Shutdown engine"""
        self._monitoring = False
        await self._aggregator.close()
    
    async def analyze_market(
        self,
        regions: List[str] = None,
        commodities: List[str] = None
    ) -> MarketIntelligence:
        """
        Generate comprehensive market intelligence
        """
        regions = regions or ["africa", "mena", "sea", "china"]
        commodities = commodities or ["oil", "gas", "metals", "grains"]
        
        # Fetch news from all categories
        all_articles = []
        for category in NewsCategory:
            articles = await self._aggregator.fetch_category(category, max_articles=30)
            all_articles.extend(articles)
        
        if not all_articles:
            return self._empty_intelligence()
        
        # Analyze sentiment
        texts = [f"{a.title} {a.summary}" for a in all_articles]
        sentiments = await self._analyzer.batch_analyze(texts)
        
        # Attach sentiment to articles
        for article, sentiment in zip(all_articles, sentiments):
            article.sentiment_score = sentiment.score
        
        # Generate risk alerts
        alerts = self._generate_alerts(all_articles, sentiments, regions, commodities)
        
        # Calculate metrics
        overall_sentiment = sum(s.score for s in sentiments) / len(sentiments)
        
        # Trend analysis (compare to previous if available)
        sentiment_trend = self._calculate_trend(all_articles)
        
        # Regional breakdown
        regional_breakdown = self._regional_analysis(all_articles, regions)
        
        # Commodity sentiment
        commodity_sentiment = self._commodity_analysis(all_articles, commodities)
        
        # Top topics
        top_topics = self._extract_topics(all_articles)
        
        # Anomaly detection
        anomaly_detected = self._detect_anomalies(sentiments)
        
        return MarketIntelligence(
            timestamp=datetime.now(),
            overall_sentiment=overall_sentiment,
            sentiment_trend=sentiment_trend,
            risk_alerts=alerts,
            top_topics=top_topics,
            regional_breakdown=regional_breakdown,
            commodity_sentiment=commodity_sentiment,
            news_volume=len(all_articles),
            anomaly_detected=anomaly_detected
        )
    
    def _generate_alerts(
        self,
        articles: List[NewsArticle],
        sentiments: List[SentimentResult],
        regions: List[str],
        commodities: List[str]
    ) -> List[RiskAlert]:
        """Generate risk alerts from analyzed content"""
        alerts = []
        
        # Group by risk type
        supply_chain_risks = []
        geopolitical_risks = []
        price_risks = []
        
        for article, sentiment in zip(articles, sentiments):
            # Check for supply chain issues
            if any(k in article.title.lower() for k in ["shortage", "supply", "production"]):
                supply_chain_risks.append((article, sentiment))
            
            # Check for geopolitical issues
            if any(k in article.title.lower() for k in ["sanctions", "war", "conflict", "tension"]):
                geopolitical_risks.append((article, sentiment))
            
            # Check for price volatility
            if any(k in article.title.lower() for k in ["surge", "plunge", "volatile", "spike"]):
                price_risks.append((article, sentiment))
        
        # Create alerts if thresholds met
        if len(supply_chain_risks) >= 3:
            alerts.append(self._create_alert(
                AlertType.SUPPLY_CHAIN,
                RiskLevel.HIGH if len(supply_chain_risks) > 5 else RiskLevel.MEDIUM,
                "Supply chain disruptions detected",
                f"{len(supply_chain_risks)} articles indicate supply chain issues",
                [a.id for a, _ in supply_chain_risks[:5]]
            ))
        
        if len(geopolitical_risks) >= 2:
            alerts.append(self._create_alert(
                AlertType.GEOPOLITICAL,
                RiskLevel.HIGH,
                "Geopolitical tensions rising",
                f"{len(geopolitical_risks)} articles report geopolitical concerns",
                [a.id for a, _ in geopolitical_risks[:5]]
            ))
        
        if len(price_risks) >= 4:
            alerts.append(self._create_alert(
                AlertType.PRICE_MOVEMENT,
                RiskLevel.MEDIUM,
                "Price volatility detected",
                f"{len(price_risks)} articles indicate price movements",
                [a.id for a, _ in price_risks[:5]]
            ))
        
        # Sentiment-based alert
        negative_ratio = sum(1 for s in sentiments if s.score < -0.3) / len(sentiments)
        if negative_ratio > 0.4:
            alerts.append(self._create_alert(
                AlertType.MARKET_SENTIMENT,
                RiskLevel.HIGH if negative_ratio > 0.6 else RiskLevel.MEDIUM,
                "Negative market sentiment dominant",
                f"{negative_ratio:.0%} of news is negative",
                []
            ))
        
        return alerts
    
    def _create_alert(
        self,
        alert_type: AlertType,
        level: RiskLevel,
        title: str,
        description: str,
        source_ids: List[str]
    ) -> RiskAlert:
        """Create a risk alert"""
        import hashlib
        
        alert_id = hashlib.md5(f"{title}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        actions = self._recommend_actions(alert_type, level)
        
        return RiskAlert(
            id=alert_id,
            type=alert_type,
            level=level,
            title=title,
            description=description,
            affected_regions=["global"],  # Simplified
            affected_commodities=["general"],
            source_articles=source_ids,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
            actions_recommended=actions,
            sentiment_trend="deteriorating" if level.value >= 3 else "stable"
        )
    
    def _recommend_actions(self, alert_type: AlertType, level: RiskLevel) -> List[str]:
        """Generate recommended actions"""
        actions = []
        
        if alert_type == AlertType.SUPPLY_CHAIN:
            actions.extend([
                "Review inventory levels for affected commodities",
                "Contact alternative suppliers",
                "Assess logistics impact"
            ])
        elif alert_type == AlertType.GEOPOLITICAL:
            actions.extend([
                "Monitor sanctions developments",
                "Review exposure to affected regions",
                "Consider hedging strategies"
            ])
        elif alert_type == AlertType.PRICE_MOVEMENT:
            actions.extend([
                "Review pricing strategy",
                "Check futures positions",
                "Alert trading desk"
            ])
        
        if level == RiskLevel.CRITICAL:
            actions.insert(0, "IMMEDIATE: Convene crisis response team")
        elif level == RiskLevel.HIGH:
            actions.insert(0, "URGENT: Escalate to management")
        
        return actions
    
    def _calculate_trend(self, articles: List[NewsArticle]) -> str:
        """Calculate sentiment trend"""
        if len(articles) < 10:
            return "insufficient_data"
        
        # Sort by time
        sorted_articles = sorted(articles, key=lambda x: x.published_at)
        mid = len(sorted_articles) // 2
        
        early_sentiment = sum(a.sentiment_score or 0 for a in sorted_articles[:mid]) / mid
        late_sentiment = sum(a.sentiment_score or 0 for a in sorted_articles[mid:]) / (len(sorted_articles) - mid)
        
        diff = late_sentiment - early_sentiment
        
        if diff > 0.2:
            return "improving"
        elif diff < -0.2:
            return "deteriorating"
        else:
            return "stable"
    
    def _regional_analysis(self, articles: List[NewsArticle], regions: List[str]) -> Dict[str, float]:
        """Analyze sentiment by region"""
        region_scores = {r: [] for r in regions}
        
        for article in articles:
            for region in regions:
                if region.lower() in article.title.lower() or region.lower() in article.content.lower():
                    if article.sentiment_score is not None:
                        region_scores[region].append(article.sentiment_score)
        
        return {
            region: sum(scores) / len(scores) if scores else 0.0
            for region, scores in region_scores.items()
        }
    
    def _commodity_analysis(self, articles: List[NewsArticle], commodities: List[str]) -> Dict[str, float]:
        """Analyze sentiment by commodity"""
        commodity_scores = {c: [] for c in commodities}
        
        for article in articles:
            for commodity in commodities:
                if commodity.lower() in article.title.lower():
                    if article.sentiment_score is not None:
                        commodity_scores[commodity].append(article.sentiment_score)
        
        return {
            comm: sum(scores) / len(scores) if scores else 0.0
            for comm, scores in commodity_scores.items()
        }
    
    def _extract_topics(self, articles: List[NewsArticle]) -> List[Dict]:
        """Extract trending topics"""
        from collections import Counter
        
        all_keywords = []
        for article in articles:
            all_keywords.extend(article.keywords[:5])
        
        top_keywords = Counter(all_keywords).most_common(10)
        
        return [
            {"topic": kw, "mentions": count, "trend": "rising"}
            for kw, count in top_keywords
        ]
    
    def _detect_anomalies(self, sentiments: List[SentimentResult]) -> bool:
        """Detect sentiment anomalies"""
        if len(sentiments) < 20:
            return False
        
        scores = [s.score for s in sentiments]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std = variance ** 0.5
        
        # Check for outliers (>2 std)
        outliers = sum(1 for s in scores if abs(s - mean) > 2 * std)
        
        return outliers > len(scores) * 0.1  # >10% outliers
    
    def _empty_intelligence(self) -> MarketIntelligence:
        """Return empty intelligence"""
        return MarketIntelligence(
            timestamp=datetime.now(),
            overall_sentiment=0.0,
            sentiment_trend="unknown",
            risk_alerts=[],
            top_topics=[],
            regional_breakdown={},
            commodity_sentiment={},
            news_volume=0,
            anomaly_detected=False
        )
    
    async def start_monitoring(self, interval_seconds: int = 300) -> None:
        """Start continuous monitoring"""
        self._monitoring = True
        
        while self._monitoring:
            try:
                intelligence = await self.analyze_market()
                logger.info(f"Monitoring cycle complete: {intelligence.news_volume} articles, "
                          f"{len(intelligence.risk_alerts)} alerts")
                
                # Store alerts
                self._alerts.extend(intelligence.risk_alerts)
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(interval_seconds)
    
    def stop_monitoring(self) -> None:
        """Stop monitoring"""
        self._monitoring = False
    
    def get_active_alerts(
        self,
        min_level: RiskLevel = RiskLevel.LOW
    ) -> List[RiskAlert]:
        """Get current active alerts"""
        now = datetime.now()
        return [
            alert for alert in self._alerts
            if alert.level.value >= min_level.value
            and (alert.expires_at is None or alert.expires_at > now)
        ]


intelligence_engine = IntelligenceEngine()
