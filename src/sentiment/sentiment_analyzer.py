"""
ACAS v2 - Sentiment Analysis Engine
Hybrid: Transformers (XLM-RoBERTa) + Rule-based fallback
Supports multilingual and aspect-based sentiment
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
import re
import json
from pathlib import Path

from src.core.config import config
from src.core.logging import get_logger
from src.core.security import secure_compare

logger = get_logger(__name__)


class SentimentLabel(Enum):
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


@dataclass
class SentimentResult:
    """Sentiment analysis result"""
    label: SentimentLabel
    score: float  # -1 to 1
    confidence: float  # 0 to 1
    aspects: Dict[str, float] = field(default_factory=dict)
    model_used: str = "unknown"
    processing_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label.value,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "aspects": {k: round(v, 4) for k, v in self.aspects.items()},
            "model": self.model_used,
            "processing_time_ms": self.processing_time_ms
        }


class TransformersSentimentAnalyzer:
    """
    Transformers-based sentiment analyzer using XLM-RoBERTa
    Supports multilingual sentiment analysis
    """

    MODEL_NAME = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    FALLBACK_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"

    def __init__(self):
        self._tokenizer = None
        self._model = None
        self._pipeline = None
        self._device = -1  # CPU by default
        self._initialized = False
        self._model_loaded = False

    async def initialize(self) -> bool:
        """Initialize transformers model with timeout protection."""
        if not config.ml.sentiment_enabled:
            logger.info("Sentiment analysis disabled in config")
            return False

        import asyncio
        import os

        # Set HF download timeout (10 min max)
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")

        async def _load_model():
            """Load the ML model with timeout."""
            from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
            import torch

            if torch.cuda.is_available():
                self._device = 0
                logger.info("Using GPU for sentiment analysis")
            else:
                self._device = -1
                logger.info("Using CPU for sentiment analysis")

            # Try to load multilingual model with timeout
            try:
                logger.info(f"Loading sentiment model: {self.MODEL_NAME}")
                self._pipeline = pipeline(
                    "sentiment-analysis",
                    model=self.MODEL_NAME,
                    tokenizer=self.MODEL_NAME,
                    device=self._device,
                    truncation=True,
                    max_length=512
                )
                self._model_loaded = True
                logger.info("Multilingual sentiment model loaded successfully")
                return True
            except Exception as e:
                logger.warning(f"Failed to load multilingual model: {e}")
                # Fallback to English model
                try:
                    logger.info(f"Loading fallback model: {self.FALLBACK_MODEL}")
                    self._pipeline = pipeline(
                        "sentiment-analysis",
                        model=self.FALLBACK_MODEL,
                        device=self._device,
                        truncation=True,
                        max_length=512
                    )
                    self._model_loaded = True
                    logger.info("Fallback English sentiment model loaded")
                    return True
                except Exception as e2:
                    logger.error(f"Failed to load fallback model: {e2}")
                    return False

        # Load model with 5-minute timeout to prevent hang
        try:
            loaded = await asyncio.wait_for(_load_model(), timeout=300)
            return loaded
        except asyncio.TimeoutError:
            logger.error("ML model loading timed out after 5 minutes — using rule-based fallback")
            return False
        except Exception as e:
            logger.error(f"Unexpected error loading ML model: {e}")
            return False

    async def analyze(self, text: str, context: Optional[str] = None) -> SentimentResult:
        """Analyze sentiment using transformers"""
        if not self._model_loaded or not self._pipeline:
            raise RuntimeError("Model not loaded")

        import time
        start_time = time.time()

        try:
            # Truncate text if too long
            max_length = 512
            if len(text) > max_length * 4:  # Rough char estimate
                text = text[:max_length * 4]

            # Run inference
            results = self._pipeline(text)

            if not results or len(results) == 0:
                raise ValueError("Empty result from model")

            result = results[0]

            # Map model output to our format
            label_str = result["label"].lower()
            score = result["score"]  # Confidence score from model

            # Convert to our label system
            if "very_negative" in label_str or (score > 0.8 and "negative" in label_str):
                label = SentimentLabel.VERY_NEGATIVE
                normalized_score = -0.8
            elif "negative" in label_str:
                label = SentimentLabel.NEGATIVE
                normalized_score = -0.4
            elif "neutral" in label_str:
                label = SentimentLabel.NEUTRAL
                normalized_score = 0.0
            elif "very_positive" in label_str or (score > 0.8 and "positive" in label_str):
                label = SentimentLabel.VERY_POSITIVE
                normalized_score = 0.8
            else:  # positive
                label = SentimentLabel.POSITIVE
                normalized_score = 0.4

            processing_time = int((time.time() - start_time) * 1000)

            return SentimentResult(
                label=label,
                score=normalized_score,
                confidence=score,
                aspects={},
                model_used=self.MODEL_NAME if self._model_loaded else self.FALLBACK_MODEL,
                processing_time_ms=processing_time
            )

        except Exception as e:
            logger.error(f"Transformers inference failed: {e}")
            raise

    async def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """Batch analyze sentiments"""
        if not self._model_loaded or not self._pipeline:
            raise RuntimeError("Model not loaded")

        try:
            # Truncate texts
            truncated_texts = [
                t[:2048] if len(t) > 2048 else t
                for t in texts
            ]

            # Batch inference
            results = self._pipeline(truncated_texts, batch_size=min(len(texts), 8))

            output = []
            for result in results:
                label_str = result["label"].lower()
                score = result["score"]

                if "negative" in label_str:
                    label = SentimentLabel.NEGATIVE
                    normalized_score = -0.4
                elif "neutral" in label_str:
                    label = SentimentLabel.NEUTRAL
                    normalized_score = 0.0
                else:
                    label = SentimentLabel.POSITIVE
                    normalized_score = 0.4

                output.append(SentimentResult(
                    label=label,
                    score=normalized_score,
                    confidence=score,
                    aspects={},
                    model_used=self.MODEL_NAME,
                    processing_time_ms=0
                ))

            return output

        except Exception as e:
            logger.error(f"Batch inference failed: {e}")
            raise


class RuleBasedSentimentAnalyzer:
    """
    Rule-based sentiment analysis (fallback)
    Optimized for supply chain and market intelligence
    """

    # Risk-related keywords for supply chain context
    RISK_KEYWORDS = {
        "supply_shortage": ["shortage", "scarcity", "out of stock", "unavailable", "depleted", "supply chain disruption"],
        "price_volatility": ["price surge", "price drop", "volatile", "fluctuation", "spike", "inflation"],
        "logistics": ["delay", "shipping", "port congestion", "transport", "backlog", "freight"],
        "geopolitical": ["sanction", "trade war", "tariff", "embargo", "restriction", "conflict"],
        "disaster": ["earthquake", "flood", "hurricane", "pandemic", "outbreak", "drought"],
        "quality": ["contamination", "recall", "defective", "substandard", "rejection"],
    }

    POSITIVE_WORDS = [
        "growth", "increase", "boom", "surge", "strong", "positive",
        "optimistic", "expansion", "profit", "success", "recovery",
        "improvement", "breakthrough", "milestone", "partnership", "investment",
        "good", "excellent", "great", "improving", "advantage",
        "stable", "resilient", "innovation", "gain"
    ]

    NEGATIVE_WORDS = [
        "decline", "decrease", "drop", "weak", "negative", "pessimistic",
        "contraction", "loss", "failure", "crisis", "risk", "concern",
        "warning", "threat", "disruption", "shortfall", "bankruptcy",
        "shortage", "congestion", "delay", "delays", "severe",
        "failing", "bad", "tension", "tensions", "flood", "floods"
    ]

    INTENSIFIERS = ["very", "extremely", "highly", "significantly", "severely", "critically"]
    NEGATORS = ["not", "no", "never", "neither", "nor", "hardly", "barely", "fails to", "lack of"]

    # Aspect keywords for aspect-based sentiment
    ASPECT_KEYWORDS = {
        "pricing": ["price", "prices", "cost", "expensive", "cheap", "affordable", "value"],
        "quality": ["quality", "standard", "grade", "certification", "inspection"],
        "delivery": ["delivery", "shipping", "arrival", "lead time", "transit"],
        "supplier": ["supplier", "vendor", "producer", "manufacturer"],
        "demand": ["demand", "consumption", "orders", "sales", "purchase"],
        "inventory": ["inventory", "stock", "warehouse", "storage"],
        "disaster": ["flood", "floods", "earthquake", "hurricane", "disaster", "drought"],
        "geopolitical": ["geopolitical", "tensions", "conflict", "war", "sanctions"],
        "logistics": ["logistics", "shipping", "port", "freight"],
    }

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize rule-based analyzer"""
        self._initialized = True
        logger.info("Rule-based sentiment analyzer initialized")
        return True

    async def analyze(self, text: str, context: Optional[str] = None) -> SentimentResult:
        """Analyze sentiment using rules"""
        import time
        start_time = time.time()

        text_lower = text.lower()
        sentences = re.split(r'[.!?]+', text_lower)

        total_score = 0.0
        total_weight = 0
        aspect_scores = {aspect: [] for aspect in self.ASPECT_KEYWORDS.keys()}

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Check for negation
            has_negation = any(neg in f" {sentence} " for neg in self.NEGATORS)

            # Count positive/negative words
            pos_matches = sum(1 for w in self.POSITIVE_WORDS if w in sentence)
            neg_matches = sum(1 for w in self.NEGATIVE_WORDS if w in sentence)

            # Check for intensifiers
            intensifier_count = sum(1 for i in self.INTENSIFIERS if i in sentence)
            intensity = 1 + 0.3 * intensifier_count

            # Calculate sentence score
            pos_score = pos_matches * intensity
            neg_score = neg_matches * intensity

            # Apply negation flip
            if has_negation:
                pos_score, neg_score = neg_score, pos_score

            sentence_score = (pos_score - neg_score) / max(pos_score + neg_score, 1)
            sentence_weight = min(len(sentence) / 100, 1.0)  # Normalize weight

            total_score += sentence_score * sentence_weight
            total_weight += sentence_weight

            # Aspect-based sentiment
            for aspect, keywords in self.ASPECT_KEYWORDS.items():
                if any(kw in sentence for kw in keywords):
                    aspect_scores[aspect].append(sentence_score)

        # Calculate final score
        if total_weight == 0:
            score = 0.0
            confidence = 0.3
        else:
            score = total_score / total_weight
            # Confidence based on word matches
            confidence = min(0.9, abs(score) * 0.5 + 0.4)

        # Map score to label
        if score > 0.6:
            label = SentimentLabel.VERY_POSITIVE
        elif score > 0.2:
            label = SentimentLabel.POSITIVE
        elif score < -0.6:
            label = SentimentLabel.VERY_NEGATIVE
        elif score < -0.2:
            label = SentimentLabel.NEGATIVE
        else:
            label = SentimentLabel.NEUTRAL

        # Aggregate aspect scores
        aspects = {}
        for aspect, scores in aspect_scores.items():
            if scores:
                aspects[aspect] = sum(scores) / len(scores)
            else:
                aspects[aspect] = 0.0

        processing_time = int((time.time() - start_time) * 1000)

        return SentimentResult(
            label=label,
            score=score,
            confidence=confidence,
            aspects=aspects,
            model_used="rule-based",
            processing_time_ms=processing_time
        )

    async def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """Analyze multiple texts"""
        return [await self.analyze(text) for text in texts]


class SentimentAnalyzer:
    """
    Hybrid sentiment analyzer
    Uses transformers if available, falls back to rule-based
    """

    def __init__(self):
        self._transformers_analyzer = TransformersSentimentAnalyzer()
        self._rule_based_analyzer = RuleBasedSentimentAnalyzer()
        self._use_transformers = False
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize sentiment analyzer (try transformers first)"""
        # Try to initialize transformers
        self._use_transformers = await self._transformers_analyzer.initialize()

        # Always initialize rule-based as fallback
        await self._rule_based_analyzer.initialize()

        self._initialized = True

        if self._use_transformers:
            logger.info("Sentiment analyzer initialized with transformers (primary) + rule-based (fallback)")
        else:
            logger.info("Sentiment analyzer initialized with rule-based only")

        return True

    async def analyze(self, text: str, context: Optional[str] = None) -> SentimentResult:
        """
        Analyze sentiment of text
        Uses transformers if available, falls back to rule-based
        """
        if not self._initialized:
            await self.initialize()

        if self._use_transformers:
            try:
                return await self._transformers_analyzer.analyze(text, context)
            except Exception as e:
                logger.warning(f"Transformers analysis failed, falling back to rule-based: {e}")
                return await self._rule_based_analyzer.analyze(text, context)
        else:
            return await self._rule_based_analyzer.analyze(text, context)

    async def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """Analyze multiple texts"""
        if not self._initialized:
            await self.initialize()

        if self._use_transformers:
            try:
                return await self._transformers_analyzer.analyze_batch(texts)
            except Exception as e:
                logger.warning(f"Batch transformers failed, falling back: {e}")
                return await self._rule_based_analyzer.analyze_batch(texts)
        else:
            return await self._rule_based_analyzer.analyze_batch(texts)

    async def analyze_with_aspects(self, text: str) -> Dict[str, Any]:
        """
        Enhanced analysis with detailed aspect breakdown
        Returns sentiment + extracted aspects + risk indicators
        """
        result = await self.analyze(text)

        # Extract risk indicators
        risk_indicators = {}
        text_lower = text.lower()

        for risk_type, keywords in RuleBasedSentimentAnalyzer.RISK_KEYWORDS.items():
            mentions = []
            for kw in keywords:
                if kw in text_lower:
                    # Find the sentence containing the keyword
                    sentences = re.split(r'[.!?]+', text)
                    for sent in sentences:
                        if kw in sent.lower():
                            mentions.append(sent.strip())
                            break

            if mentions:
                risk_indicators[risk_type] = {
                    "mentioned": True,
                    "context": mentions[:3],  # Top 3 mentions
                    "sentiment": result.aspects.get(risk_type, 0.0)
                }

        return {
            "sentiment": result.to_dict(),
            "risk_indicators": risk_indicators,
            "summary": self._generate_summary(result, risk_indicators)
        }

    def _generate_summary(self, result: SentimentResult, risk_indicators: Dict) -> str:
        """Generate human-readable summary"""
        summary_parts = []

        # Sentiment summary
        if result.label == SentimentLabel.VERY_POSITIVE:
            summary_parts.append("Very positive sentiment detected.")
        elif result.label == SentimentLabel.POSITIVE:
            summary_parts.append("Positive sentiment detected.")
        elif result.label == SentimentLabel.NEUTRAL:
            summary_parts.append("Neutral sentiment.")
        elif result.label == SentimentLabel.NEGATIVE:
            summary_parts.append("Negative sentiment detected.")
        else:
            summary_parts.append("Very negative sentiment detected.")

        # Risk summary
        high_risk = [k for k, v in risk_indicators.items() if v.get("sentiment", 0) < -0.3]
        if high_risk:
            summary_parts.append(f"High risk detected in: {', '.join(high_risk)}.")

        return " ".join(summary_parts)


# Global instance
sentiment_analyzer = SentimentAnalyzer()
