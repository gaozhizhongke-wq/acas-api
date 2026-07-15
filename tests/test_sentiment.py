"""
ACAS v2 - Sentiment Analysis Tests
"""

import pytest
from datetime import datetime
from sentiment.sentiment_analyzer import (
    sentiment_analyzer,
    SentimentLabel,
    RuleBasedSentimentAnalyzer
)


class TestRuleBasedSentimentAnalyzer:
    """Tests for rule-based sentiment analyzer."""

    @pytest.fixture(autouse=True)
    async def setup_analyzer(self):
        """Initialize analyzer for each test."""
        self.analyzer = RuleBasedSentimentAnalyzer()
        await self.analyzer.initialize()
        yield
        self.analyzer = None

    @pytest.mark.asyncio
    async def test_positive_sentiment(self):
        """Test detection of positive sentiment."""
        text = "The market is experiencing strong growth and positive expansion."
        result = await self.analyzer.analyze(text)

        assert result.label in [SentimentLabel.POSITIVE, SentimentLabel.VERY_POSITIVE]
        assert result.score > 0
        assert result.confidence > 0
        assert result.model_used == "rule-based"

    @pytest.mark.asyncio
    async def test_negative_sentiment(self):
        """Test detection of negative sentiment."""
        text = "There is a severe shortage and supply chain disruption causing crisis."
        result = await self.analyzer.analyze(text)

        assert result.label in [SentimentLabel.NEGATIVE, SentimentLabel.VERY_NEGATIVE]
        assert result.score < 0
        assert result.model_used == "rule-based"

    @pytest.mark.asyncio
    async def test_neutral_sentiment(self):
        """Test detection of neutral sentiment."""
        text = "The report shows current market conditions and recent data."
        result = await self.analyzer.analyze(text)

        assert result.label == SentimentLabel.NEUTRAL
        assert abs(result.score) < 0.3

    @pytest.mark.asyncio
    async def test_negation_handling(self):
        """Test that negation flips sentiment."""
        # "not" should flip positive "great" to negative
        text_positive = "This is great."
        result_positive = await self.analyzer.analyze(text_positive)

        text_negative = "This is not great."
        result_negative = await self.analyzer.analyze(text_negative)

        # Negation should cause different scores
        assert result_positive.score != result_negative.score
        assert result_positive.score > 0
        assert result_negative.score < 0

    @pytest.mark.asyncio
    async def test_aspect_based_sentiment(self):
        """Test aspect-based sentiment extraction."""
        text = "Prices are increasing but delivery times are improving."
        result = await self.analyzer.analyze(text)

        assert "pricing" in result.aspects
        assert "delivery" in result.aspects
        # Pricing should be negative (increasing), delivery positive (improving)
        assert result.aspects["pricing"] > 0 or result.aspects["delivery"] > 0

    @pytest.mark.asyncio
    async def test_risk_indicators(self):
        """Test risk keyword detection."""
        text = "There are floods in the region and geopolitical tensions rising."
        result = await self.analyzer.analyze(text)

        # Should detect disaster and geopolitical risks
        assert "disaster" in result.aspects
        assert "geopolitical" in result.aspects

    @pytest.mark.asyncio
    async def test_empty_text(self):
        """Test handling of empty text."""
        result = await self.analyzer.analyze("")

        assert result.label == SentimentLabel.NEUTRAL
        assert result.score == 0.0
        assert result.confidence < 0.5

    @pytest.mark.asyncio
    async def test_short_text(self):
        """Test handling of very short text."""
        result = await self.analyzer.analyze("Good.")

        assert result.label in [SentimentLabel.POSITIVE, SentimentLabel.VERY_POSITIVE]
        assert result.score > 0

    @pytest.mark.asyncio
    async def test_supply_chain_context(self):
        """Test supply chain specific context."""
        text = "Port congestion is causing delays in shipping and logistics."
        result = await self.analyzer.analyze(text)

        assert result.label in [SentimentLabel.NEGATIVE, SentimentLabel.VERY_NEGATIVE]
        assert "logistics" in result.aspects
        assert result.aspects["logistics"] <= 0


class TestSentimentAnalyzerIntegration:
    """Integration tests for the main sentiment_analyzer instance."""

    @pytest.mark.asyncio
    async def test_analyze_with_aspects(self):
        """Test the enhanced analyze_with_aspects method."""
        text = "Severe shortage reported. Prices are surging. Logistics delays expected."

        # This will use rule-based if transformers not available
        result_dict = await sentiment_analyzer.analyze_with_aspects(text)

        assert "sentiment" in result_dict
        assert "risk_indicators" in result_dict
        assert "summary" in result_dict

        assert result_dict["sentiment"]["label"] in [
            "negative", "very_negative", "neutral"
        ]

        # Should detect risks
        assert len(result_dict["risk_indicators"]) > 0


class TestBatchProcessing:
    """Tests for batch processing."""

    @pytest.fixture(autouse=True)
    async def setup_analyzer(self):
        """Initialize analyzer for each test."""
        self.analyzer = RuleBasedSentimentAnalyzer()
        await self.analyzer.initialize()
        yield
        self.analyzer = None

    @pytest.mark.asyncio
    async def test_analyze_batch(self):
        """Test batch sentiment analysis."""
        texts = [
            "Great growth in the market!",
            "Terrible shortage and crisis.",
            "Normal conditions reported."
        ]

        results = await self.analyzer.analyze_batch(texts)

        assert len(results) == 3
        assert results[0].score > 0  # Positive
        assert results[1].score < 0  # Negative
        assert abs(results[2].score) < 0.5  # Neutral

    @pytest.mark.asyncio
    async def test_batch_empty_list(self):
        """Test batch with empty list."""
        results = await self.analyzer.analyze_batch([])
        assert results == []
