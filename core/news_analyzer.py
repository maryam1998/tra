"""
Fetches recent headlines for a symbol and produces a light sentiment
signal. This module never outputs prices or trade parameters — its
only job is qualitative context that gets attached to the AI agent's
prompt (news headlines + a coarse sentiment score).
"""
from __future__ import annotations

from typing import List

import requests

from core.models import NewsAssessment

HIGH_IMPACT_KEYWORDS = [
    "hack", "exploit", "regulation", "ban", "sec", "lawsuit", "collapse",
    "bankruptcy", "war", "sanction", "rate hike", "rate cut", "inflation",
    "etf approval", "etf rejected", "delist",
]

POSITIVE_KEYWORDS = [
    "surge", "rally", "approval", "partnership", "adoption", "record high",
    "upgrade", "bullish", "growth", "beat expectations",
]
NEGATIVE_KEYWORDS = [
    "crash", "plunge", "sell-off", "downgrade", "bearish", "miss expectations",
    "fraud", "hack", "ban", "lawsuit",
]


class NewsAnalyzer:
    def __init__(self, cryptopanic_api_key: str = "", news_api_key: str = ""):
        self.cryptopanic_api_key = cryptopanic_api_key
        self.news_api_key = news_api_key

    def _fetch_cryptopanic(self, symbol: str, limit: int = 10) -> List[str]:
        if not self.cryptopanic_api_key:
            return []
        base_currency = symbol.split("_")[0].split("/")[0]
        resp = requests.get(
            "https://cryptopanic.com/api/v1/posts/",
            params={"auth_token": self.cryptopanic_api_key, "currencies": base_currency, "public": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return [post["title"] for post in data.get("results", [])[:limit]]

    def _fetch_newsapi(self, symbol: str, limit: int = 10) -> List[str]:
        if not self.news_api_key:
            return []
        query = symbol.split("_")[0].split("/")[0]
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "sortBy": "publishedAt", "language": "en", "pageSize": limit,
                    "apiKey": self.news_api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return [a["title"] for a in data.get("articles", [])[:limit]]

    @staticmethod
    def _score_headlines(headlines: List[str]) -> tuple[float, bool]:
        if not headlines:
            return 0.0, False
        pos = sum(1 for h in headlines if any(k in h.lower() for k in POSITIVE_KEYWORDS))
        neg = sum(1 for h in headlines if any(k in h.lower() for k in NEGATIVE_KEYWORDS))
        high_impact = any(any(k in h.lower() for k in HIGH_IMPACT_KEYWORDS) for h in headlines)
        total = pos + neg
        sentiment = 0.0 if total == 0 else (pos - neg) / total
        return sentiment, high_impact

    def analyze(self, symbol: str) -> NewsAssessment:
        headlines: List[str] = []
        try:
            headlines += self._fetch_cryptopanic(symbol)
        except Exception:
            pass
        try:
            headlines += self._fetch_newsapi(symbol)
        except Exception:
            pass

        sentiment, high_impact = self._score_headlines(headlines)
        summary = (
            f"{len(headlines)} recent headlines, sentiment={sentiment:+.2f}"
            + (", HIGH-IMPACT EVENT DETECTED" if high_impact else "")
        )
        return NewsAssessment(
            symbol=symbol,
            headlines=headlines[:5],
            sentiment_score=sentiment,
            has_high_impact_event=high_impact,
            summary=summary,
        )
