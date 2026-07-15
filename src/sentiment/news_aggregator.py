"""
ACAS v2 - News Aggregation Engine
Multi-source news collection with deduplication
Supports RSS, NewsAPI, and GDELT Project
"""

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Any
from enum import Enum
import asyncio
import aiohttp
import json
from urllib.parse import urlencode

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSOR_AVAILABLE = False
    feedparser = None

from core.config import config
from core.logging import get_logger

logger = get_logger(__name__)


class NewsCategory(Enum):
    BUSINESS = "business"
    TECH = "tech"
    FINANCE = "finance"
    POLITICS = "politics"
    COMMODITY = "commodity"
    LOGISTICS = "logistics"
    DISASTER = "disaster"
    SECURITY = "security"
    AGRICULTURE = "agriculture"
    ENERGY = "energy"


@dataclass
class NewsArticle:
    """Normalized news article"""
    id: str
    title: str
    content: str
    summary: str
    source: str
    source_url: str
    category: NewsCategory
    published_at: datetime
    language: str
    entities: List[Dict] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    sentiment_score: Optional[float] = None
    relevance_score: float = 0.0
    related_regions: List[str] = field(default_factory=list)
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            self.hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        content = f"{self.title}:{self.source}:{self.published_at.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class NewsAggregator:
    """
    Multi-source news aggregation
    Sources: RSS feeds, NewsAPI, GDELT Project
    """
    
    # RSS Feeds by category
    RSS_FEEDS = {
        NewsCategory.BUSINESS: [
            ("https://feeds.reuters.com/reuters/businessNews", "Reuters Business"),
            ("https://feeds.bbci.co.uk/news/business/rss.xml", "BBC Business"),
            ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera"),
        ],
        NewsCategory.FINANCE: [
            ("https://www.cnbc.com/id/19746125/device/rss/rss.xml", "CNBC"),
            ("https://rss.nytimes.com/services/xml/rss/nyt/Finance.xml", "NYT Finance"),
        ],
        NewsCategory.COMMODITY: [
            ("https://www.reuters.com/news/archive/commoditiesNews.rss", "Reuters Commodities"),
            ("https://feeds.bloomberg.com/markets/news.rss", "Bloomberg Markets"),
        ],
        NewsCategory.AGRICULTURE: [
            ("https://www.fao.org/news/rss.xml", "FAO News"),
            ("https://www.agweb.com/rss/all", "AgWeb"),
        ],
        # Africa-specific sources
        "africa": [
            ("https://allafrica.com/tools/headlines/rdf/business/headlines.rdf", "AllAfrica Business"),
            ("https://www.africanews.com/feed/", "Africanews"),
            ("https://www.theeastafrican.co.ke/feed/", "The EastAfrican"),
            ("https://www.businessdailyafrica.com/feed/", "Business Daily Africa"),
            ("https://www.ghanabusinessnews.com/rss.php", "Ghana Business News"),
            ("https://www.engineeringnews.co.za/rss/economy", "Engineering News"),
        ],
        # Commodity-specific sources
        "commodities_extended": [
            ("https://www.indexbox.io/blog/rss", "IndexBox"),
            ("https://www.itc-trade.com/rss", "ITC Trade"),
            ("https://www.world-grain.com/rss.html", "World Grain"),
            ("https://www.spglobal.com/platts/en/rss", "S&P Global Platts"),
        ]
    }
    
    # GDELT Project API endpoint
    GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._seen_hashes: Set[str] = set()
        self._news_api_key: Optional[str] = None
        self._gdelt_enabled: bool = True
        
    async def initialize(self) -> None:
        """Initialize news aggregator"""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": "ACAS-NewsBot/2.0"}
        )
        
        # Load API keys from config
        self._news_api_key = getattr(config, 'news_api_key', None)
        
        logger.info("News aggregator initialized", extra={
            "news_api_configured": self._news_api_key is not None,
            "gdelt_enabled": self._gdelt_enabled
        })
    
    async def close(self) -> None:
        """Close HTTP session"""
        if self._session:
            await self._session.close()
    
    async def fetch_category(
        self,
        category: NewsCategory,
        max_articles: int = 50,
        hours_back: int = 24,
        include_africa: bool = True,
        include_commodities: bool = True
    ) -> List[NewsArticle]:
        """
        Fetch news for a category from all available sources
        """
        tasks = []
        
        # RSS feeds for main category
        feeds = self.RSS_FEEDS.get(category, [])
        for url, source_name in feeds:
            tasks.append(self._fetch_rss_feed(url, source_name, category, hours_back))
        
        # Africa-specific sources
        if include_africa and "africa" in self.RSS_FEEDS:
            for url, source_name in self.RSS_FEEDS["africa"]:
                tasks.append(self._fetch_rss_feed(url, source_name, category, hours_back))
        
        # Commodity-specific sources
        if include_commodities and "commodities_extended" in self.RSS_FEEDS:
            for url, source_name in self.RSS_FEEDS["commodities_extended"]:
                tasks.append(self._fetch_rss_feed(url, source_name, NewsCategory.COMMODITY, hours_back))
        
        # NewsAPI (if configured)
        if self._news_api_key:
            tasks.append(self._fetch_news_api(category, hours_back))
        
        # GDELT Project (always available, free)
        if self._gdelt_enabled:
            tasks.append(self._fetch_gdelt(category, hours_back))
        
        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        articles = []
        for result in results:
            if isinstance(result, list):
                articles.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"News fetch error: {result}")
        
        # Deduplicate
        unique_articles = self._deduplicate(articles)
        
        # Sort by relevance and recency
        unique_articles.sort(
            key=lambda x: (x.relevance_score * 0.3 + self._recency_score(x.published_at) * 0.7),
            reverse=True
        )
        
        return unique_articles[:max_articles]
    
    async def _fetch_rss_feed(
        self,
        url: str,
        source_name: str,
        category: NewsCategory,
        hours_back: int
    ) -> List[NewsArticle]:
        """Fetch and parse RSS feed"""
        if not self._session:
            return []
        
        if not FEEDPARSOR_AVAILABLE or feedparser is None:
            logger.warning("feedparser not available, skipping RSS parsing")
            return []
        
        try:
            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"RSS fetch failed: {url} - status {response.status}")
                    return []
                
                content = await response.text()
                feed = feedparser.parse(content)
                
                articles = []
                cutoff = datetime.now() - timedelta(hours=hours_back)
                
                for entry in feed.entries[:50]:  # Limit per feed
                    published = self._parse_date(entry.get("published", ""))
                    if published and published < cutoff:
                        continue
                    
                    # Calculate relevance score
                    relevance = self._calculate_relevance(entry, category)
                    
                    article = NewsArticle(
                        id=f"rss_{hashlib.md5(entry.link.encode()).hexdigest()[:12]}",
                        title=entry.get("title", "")[:200],
                        content=entry.get("summary", entry.get("description", ""))[:2000],
                        summary=entry.get("summary", "")[:500],
                        source=source_name,
                        source_url=entry.link,
                        category=category,
                        published_at=published or datetime.now(),
                        language=self._detect_language(entry),
                        relevance_score=relevance
                    )
                    articles.append(article)
                
                logger.info(f"Fetched {len(articles)} articles from {source_name}")
                return articles
                
        except asyncio.TimeoutError:
            logger.warning(f"RSS fetch timeout: {url}")
            return []
        except Exception as e:
            logger.warning(f"RSS fetch failed for {url}: {e}")
            return []
    
    async def _fetch_news_api(
        self,
        category: NewsCategory,
        hours_back: int
    ) -> List[NewsArticle]:
        """Fetch from NewsAPI (requires API key)"""
        if not self._news_api_key or not self._session:
            return []
        
        # Map category to NewsAPI category
        category_map = {
            NewsCategory.BUSINESS: "business",
            NewsCategory.TECH: "technology",
            NewsCategory.FINANCE: "business",
            NewsCategory.POLITICS: "politics",
        }
        
        news_api_category = category_map.get(category, "general")
        
        params = {
            "apiKey": self._news_api_key,
            "category": news_api_category,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 50,
            "q": self._get_search_query(category)  # Add relevant keywords
        }
        
        try:
            url = f"https://newsapi.org/v2/top-headlines?{urlencode(params)}"
            
            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"NewsAPI request failed: {response.status}")
                    return []
                
                data = await response.json()
                
                if data.get("status") != "ok":
                    logger.warning(f"NewsAPI error: {data.get('message')}")
                    return []
                
                articles = []
                cutoff = datetime.now() - timedelta(hours=hours_back)
                
                for article_data in data.get("articles", []):
                    published = self._parse_date(article_data.get("publishedAt", ""))
                    if published and published < cutoff:
                        continue
                    
                    article = NewsArticle(
                        id=f"newsapi_{hashlib.md5(article_data['url'].encode()).hexdigest()[:12]}",
                        title=article_data.get("title", "")[:200],
                        content=article_data.get("content", "") or article_data.get("description", ""),
                        summary=article_data.get("description", "")[:500],
                        source=article_data.get("source", {}).get("name", "NewsAPI"),
                        source_url=article_data.get("url", ""),
                        category=category,
                        published_at=published or datetime.now(),
                        language="en",
                        relevance_score=0.8  # NewsAPI articles are generally relevant
                    )
                    articles.append(article)
                
                logger.info(f"Fetched {len(articles)} articles from NewsAPI")
                return articles
                
        except Exception as e:
            logger.error(f"NewsAPI fetch failed: {e}")
            return []
    
    async def _fetch_gdelt(
        self,
        category: NewsCategory,
        hours_back: int
    ) -> List[NewsArticle]:
        """
        Fetch from GDELT Project (free, global event database)
        GDELT covers 100+ languages and tracks news from around the world
        """
        if not self._session:
            return []
        
        # Calculate times for GDELT
        end_date = datetime.now()
        start_date = end_date - timedelta(hours=hours_back)
        
        # Format: YYYYMMDDHHMMSS
        start_str = start_date.strftime("%Y%m%d%H%M%S")
        end_str = end_date.strftime("%Y%m%d%H%M%S")
        
        # Build query
        query = self._get_gdelt_query(category)
        
        params = {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "startdatetime": start_str,
            "enddatetime": end_str,
            "maxrecords": 100,
        }
        
        try:
            url = f"{self.GDELT_API}?{urlencode(params)}"
            
            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"GDELT request failed: {response.status}")
                    return []
                
                data = await response.json()
                
                articles = []
                
                for item in data.get("articles", []):
                    # Parse GDELT date format
                    published_str = item.get("seendate", "")
                    try:
                        published = datetime.strptime(published_str[:14], "%Y%m%d%H%M%S")
                    except:
                        published = datetime.now()
                    
                    # Extract article
                    article = NewsArticle(
                        id=f"gdelt_{item.get('articleid', hashlib.md5(item.get('url', '').encode()).hexdigest()[:12])}",
                        title=item.get("title", "")[:200],
                        content=item.get("snippet", "")[:1000],
                        summary=item.get("snippet", "")[:500],
                        source=item.get("sourcecountry", "GDELT"),
                        source_url=item.get("url", ""),
                        category=category,
                        published_at=published,
                        language=item.get("language", "en"),
                        relevance_score=0.6,  # GDELT is broader, lower relevance
                        related_regions=[item.get("sourcecountry", "")]
                    )
                    articles.append(article)
                
                logger.info(f"Fetched {len(articles)} articles from GDELT")
                return articles
                
        except Exception as e:
            logger.error(f"GDELT fetch failed: {e}")
            return []
    
    def _get_search_query(self, category: NewsCategory) -> str:
        """Get search keywords for NewsAPI"""
        queries = {
            NewsCategory.COMMODITY: "commodity OR wheat OR maize OR rice OR coffee OR supply chain",
            NewsCategory.AGRICULTURE: "agriculture OR farming OR crop OR harvest OR food security",
            NewsCategory.BUSINESS: "business OR market OR economy OR trade",
            NewsCategory.LOGISTICS: "logistics OR shipping OR port OR transport OR supply chain",
            NewsCategory.DISASTER: "disaster OR flood OR drought OR earthquake OR hurricane",
        }
        return queries.get(category, "")
    
    def _get_gdelt_query(self, category: NewsCategory) -> str:
        """Get GDELT query string"""
        # GDELT uses advanced query syntax
        queries = {
            NewsCategory.COMMODITY: "wheat OR maize OR rice OR coffee OR commodity (supply OR shortage OR price)",
            NewsCategory.AGRICULTURE: "agriculture OR farming OR crop (harvest OR failure OR drought)",
            NewsCategory.LOGISTICS: "logistics OR shipping OR port (congestion OR delay OR strike)",
            NewsCategory.DISASTER: "disaster OR flood OR earthquake OR drought (Africa OR Africa)",
        }
        return queries.get(category, "Africa commodity")
    
    def _calculate_relevance(self, entry: Dict, category: NewsCategory) -> float:
        """Calculate article relevance score (0-1)"""
        title = entry.get("title", "").lower()
        summary = entry.get("summary", "").lower()
        text = f"{title} {summary}"
        
        # Category keywords
        keywords = {
            NewsCategory.COMMODITY: ["wheat", "maize", "rice", "commodity", "grain", "food"],
            NewsCategory.AGRICULTURE: ["agriculture", "farming", "crop", "harvest", "farm"],
            NewsCategory.LOGISTICS: ["logistics", "shipping", "port", "transport", "supply"],
            NewsCategory.DISASTER: ["disaster", "flood", "drought", "earthquake", "crisis"],
        }
        
        category_keywords = keywords.get(category, [])
        
        # Count keyword matches
        matches = sum(1 for kw in category_keywords if kw in text)
        
        # Normalize score
        score = min(matches / max(len(category_keywords), 1), 1.0)
        
        # Boost score if keywords in title
        title_matches = sum(1 for kw in category_keywords if kw in title)
        score += title_matches * 0.2
        
        return min(score, 1.0)
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats"""
        if not date_str:
            return None
        
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            pass
        
        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except:
                pass
        
        return None
    
    def _detect_language(self, entry: Dict) -> str:
        """Detect article language (simplified)"""
        # Check if feed provides language
        if hasattr(entry, 'feed') and hasattr(entry.feed, 'language'):
            return entry.feed.language[:2]
        
        # Default to English
        return "en"
    
    def _recency_score(self, published_at: datetime) -> float:
        """Calculate recency score (1.0 = very recent, 0.0 = old)"""
        age_hours = (datetime.now() - published_at).total_seconds() / 3600
        
        if age_hours < 1:
            return 1.0
        elif age_hours < 6:
            return 0.8
        elif age_hours < 24:
            return 0.6
        elif age_hours < 72:
            return 0.3
        else:
            return 0.1
    
    def _deduplicate(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Remove duplicate articles based on title hash"""
        seen = set()
        unique = []
        
        for article in articles:
            if article.hash not in seen:
                seen.add(article.hash)
                unique.append(article)
        
        return unique
    
    async def fetch_trending_topics(
        self,
        categories: List[NewsCategory],
        hours_back: int = 24
    ) -> Dict[str, int]:
        """
        Fetch trending topics across categories
        Returns: {topic: mention_count}
        """
        all_articles = []
        
        for category in categories:
            articles = await self.fetch_category(
                category,
                max_articles=100,
                hours_back=hours_back,
                include_africa=True,
                include_commodities=True
            )
            all_articles.extend(articles)
        
        # Extract keywords and count
        from collections import Counter
        import re
        
        keyword_counter = Counter()
        
        for article in all_articles:
            # Extract meaningful words (simplified)
            text = f"{article.title} {article.summary}".lower()
            words = re.findall(r'\b[a-z]{4,}\b', text)  # Words with 4+ chars
            
            # Filter out common words
            stop_words = {"this", "that", "with", "from", "have", "been", "were", "they", "their"}
            filtered_words = [w for w in words if w not in stop_words]
            
            keyword_counter.update(filtered_words)
        
        # Return top 20 trending topics
        return dict(keyword_counter.most_common(20))


news_aggregator = NewsAggregator()
