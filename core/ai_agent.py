"""
AI Agent — the "which opportunity is actually good" reasoning layer.

Hard rule enforced by design, not just by prompting: this class's
return type (AIAssessment) has no price, quantity, leverage, or
percentage-of-capital field. Even if the model ignores instructions
and emits numbers in its rationale text, those numbers are never
parsed into anything the rest of the pipeline uses — TechnicalSignal
+ RiskManager alone determine entry/stop/target/size/leverage.

This agent tries a prioritized chain of LLM providers (see
core/ai_providers.py and config.AI_PROVIDER_PRIORITY) and uses the
first one that returns a valid, parseable response. If a provider
errors out, is rate-limited, or returns garbage, the next one in the
chain is tried automatically — that's how "use all the free models"
works in practice: as a fallback chain, not a simultaneous ensemble.

If no provider is configured (or every one fails), this falls back to
a transparent rule-based assessment derived purely from the technical
score, so the system remains fully functional (offline mode) while
clearly labeling that fallback in AIAssessment.source.
"""
from __future__ import annotations

import json
from typing import List

from core.ai_providers import ProviderConfig, call_provider
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


def _strip_json_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()


class AIAgent:
    def __init__(self, providers: List[ProviderConfig], timeout: int = 30):
        # Only keep providers that actually have what they need to be called
        # (an API key, or a free anonymous tier that needs none).
        self.providers = [p for p in providers if p.is_usable]
        self.timeout = timeout

    @property
    def is_online(self) -> bool:
        return bool(self.providers)

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
            f"Rule-based fallback (no AI provider available): technical score {technical.score:.0f}, "
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
        user_content = json.dumps(user_payload)

        errors: List[str] = []
        for provider in self.providers:
            try:
                text = call_provider(provider, SYSTEM_PROMPT, user_content, self.timeout)
                parsed = json.loads(_strip_json_fences(text))

                direction = Direction(parsed.get("direction", "none"))
                conviction = float(parsed.get("conviction", 0))
                rationale = str(parsed.get("rationale", ""))[:400]

                return AIAssessment(
                    symbol=technical.symbol,
                    direction=direction,
                    conviction=max(0.0, min(100.0, conviction)),
                    rationale=f"[{provider.name}] {rationale}",
                    source=f"ai:{provider.name}",
                )
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                continue  # try the next provider in the priority chain

        fallback = self._rule_based_fallback(technical, news)
        fallback.rationale = f"[all {len(self.providers)} AI providers failed: {'; '.join(errors)}] " + fallback.rationale
        return fallback
