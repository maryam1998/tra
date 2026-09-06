"""
Cross-market ranking: turns a pile of per-symbol opportunities (some
crypto, some stocks, some forex, some gold) into a short ordered list
of the genuinely best ones, so Telegram only ever hears about the
strongest candidate(s) instead of every mildly interesting setup.
"""
from __future__ import annotations

from typing import List

from core.models import Opportunity


def compute_composite_score(technical_score: float, ai_conviction: float) -> float:
    # Weighted blend: technical math and AI judgement contribute
    # roughly equally, so neither can dominate on its own.
    return 0.5 * technical_score + 0.5 * ai_conviction


class OpportunityRanker:
    def __init__(self, min_score: float, max_alerts_per_cycle: int = 3):
        self.min_score = min_score
        self.max_alerts_per_cycle = max_alerts_per_cycle

    def rank(self, opportunities: List[Opportunity]) -> List[Opportunity]:
        qualified = [
            o for o in opportunities
            if o.approved and o.composite_score >= self.min_score
        ]
        qualified.sort(key=lambda o: o.composite_score, reverse=True)
        return qualified[: self.max_alerts_per_cycle]
