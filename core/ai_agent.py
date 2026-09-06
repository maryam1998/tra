"""
AI Agent — the "which opportunity is actually good" reasoning layer.

Hard rule enforced by design, not just by prompting: this class's
return type (AIAssessment) has no price, quantity, leverage, or
percentage-of-capital field. Even if the model ignores instructions
and emits numbers in its rationale text, those numbers are never
parsed into anything the rest of the pipeline uses — TechnicalSignal
+ RiskManager alone determine entry/stop/target/size/leverage.

If ANTHROPIC_API_KEY is not configured, this falls back to a
transparent rule-based assessment derived purely from the technical
score, so the system remains fully functional (offline mode) while
clearly labeling that fallback in AIAssessment.source.
"""
from __future__ import annotations

import json

import requests

from core.models import AIAssessment, Direction, NewsAssessment, TechnicalSignal

SYSTEM_PROMPT = """You are a market-analysis assistant inside an automated pipeline.
You will be given already-computed technical indicators and recent news headlines
for one symbol. Your ONLY job is to judge whether this looks like a genuinely good
trading opportunity worth surfacing to the user, and to explain why in plain language.

STRICT RULES:
- Do NOT output any price, percentage, position size, leverage, or quantity.
  Those are computed elsewhere from real market data and risk rules, never from you.
- Respond with STRICT JSON only, no markdown fences, no extra text, matching:
  {"direction": "long" | "short" | "none", "conviction": <0-100 integer>, "rationale": "<= 40 words"}
- Use "none" whenever the technical picture is mixed, the news is high-impact/uncertain,
  or conviction would be low. Do not force a directional call when the evidence is weak.
"""


class AIAgent:
    def __init__(self, api_key: str, model: str, timeout: int = 30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def is_online(self) -> bool:
        return bool(self.api_key)

    def _rule_based_fallback(self, technical: TechnicalSignal, news: NewsAssessment) -> AIAssessment:
        direction = technical.bias
        conviction = technical.score
        if news.has_high_impact_event:
            conviction *= 0.6  # be more cautious around high-impact news
        if news.sentiment_score < -0.3 and direction == Direction.LONG:
            conviction *= 0.7
        if news.sentiment_score > 0.3 and direction == Direction.SHORT:
            conviction *= 0.7

        rationale = (
            f"Rule-based fallback (no AI key configured): technical score {technical.score:.0f}, "
            f"bias {direction.value}, news sentiment {news.sentiment_score:+.2f}."
        )
        return AIAssessment(
            symbol=technical.symbol,
            direction=direction,
            conviction=max(0.0, min(100.0, conviction)),
            rationale=rationale,
            source="rule_based_fallback",
        )

    def assess(self, technical: TechnicalSignal, news: NewsAssessment) -> AIAssessment:
        if not self.is_online:
            return self._rule_based_fallback(technical, news)

        user_payload = {
            "symbol": technical.symbol,
            "asset_class": technical.asset_class.value,
            "technical_indicators": {
                "ema_fast": round(technical.ema_fast, 4),
                "ema_slow": round(technical.ema_slow, 4),
                "rsi": round(technical.rsi, 1),
                "macd_hist": round(technical.macd_hist, 4),
                "atr": round(technical.atr, 4),
                "volume_ratio": round(technical.volume_ratio, 2),
                "momentum_pct": round(technical.momentum, 2),
                "rule_based_score_0_100": round(technical.score, 1),
                "rule_based_bias": technical.bias.value,
            },
            "news": {
                "sentiment_score": news.sentiment_score,
                "high_impact_event": news.has_high_impact_event,
                "recent_headlines": news.headlines,
            },
        }

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 300,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": json.dumps(user_payload)}],
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(block.get("text", "") for block in data.get("content", []))
            parsed = json.loads(text)

            direction = Direction(parsed.get("direction", "none"))
            conviction = float(parsed.get("conviction", 0))
            rationale = str(parsed.get("rationale", ""))[:400]

            return AIAssessment(
                symbol=technical.symbol,
                direction=direction,
                conviction=max(0.0, min(100.0, conviction)),
                rationale=rationale,
                source="ai",
            )
        except Exception as exc:
            fallback = self._rule_based_fallback(technical, news)
            fallback.rationale = f"[AI call failed: {exc}] " + fallback.rationale
            return fallback
